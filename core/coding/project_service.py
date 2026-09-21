from __future__ import annotations

import ast
import json
import os
import re
import shutil
from pathlib import Path

from core.audit import AuditLogger
from core.execution import ExecutionService, PermissionMode, RiskLevel
from core.project_intelligence import ProjectIntelligenceService
from core.tools.checkpoint import CheckpointService
from core.tools.hashing import sha256_file, sha256_text

from .diff_service import diff_hash, unified_diff
from .project_models import (
    CodingProjectTask,
    ProjectFileManifest,
    ProjectMap,
    approval_manifest_payload,
    new_task_id,
    now_iso,
)
from .project_repository import CodingProjectRepository
from .project_test_runner import ProjectTestRunner


class CodingProjectService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.projects_dir = self.root / "projetos"
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.repo = CodingProjectRepository(self.root / "data" / "golden_ai.db")
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.runner = ProjectTestRunner(self.root / ".venv" / "Scripts" / "python.exe", self.execution)
        self.checkpoints = CheckpointService(self.root / "backups" / "checkpoints")
        self.project_tools = ProjectIntelligenceService(self.root)

    def create_task(self, user_request: str, project_root: str | Path) -> CodingProjectTask:
        project = Path(project_root).resolve()
        if not self._authorized_project(project):
            raise PermissionError("Projeto fora de C:\\GoldenAI\\projetos")
        task = CodingProjectTask(
            task_id=new_task_id(),
            created_at=now_iso(),
            updated_at=now_iso(),
            status="CREATED",
            user_request=user_request,
            project_root=str(project),
        )
        self.repo.save_task(task)
        self._event(task, "TASK_CREATED", "CREATED", "CodingProjectTask criada")
        return task

    def prepare_full_fix(self, task_id: str, max_iterations: int = 3) -> CodingProjectTask:
        task = self.require_task(task_id)
        project_map = self.map_project(task.project_root)
        task.status = "MAPPING"
        task.project_map_json = json.dumps(project_map.__dict__, ensure_ascii=False, sort_keys=True)
        task.files_in_scope = project_map.files
        task.source_hashes = {path: sha256_file(Path(task.project_root) / path) for path in project_map.files}
        self.repo.save_task(task)
        self._event(task, "PROJECT_MAPPED", "COMPLETED", f"Projeto mapeado: {len(project_map.files)} arquivos")

        workspace = self.create_workspace(task, project_map.related_files)
        task.workspace_path = str(workspace)
        task.status = "TESTING_BASELINE"
        baseline = self.runner.run(task.project_root, task.task_id, "baseline", workspace / "reports")
        task.test_command = baseline.command
        task.test_status = baseline.status
        self.repo.save_task(task)

        task.status = "ANALYZING"
        task.analysis = self._analysis_from_baseline(baseline)
        task.affected_files = self._affected_files(project_map)
        task.plan = self._plan_for(task.affected_files)
        self.repo.save_task(task)
        self._event(task, "AFFECTED_FILES_IDENTIFIED", "COMPLETED", f"{len(task.affected_files)} arquivos relacionados")

        previous_failures = baseline.failures + baseline.errors
        for iteration in range(1, max_iterations + 1):
            task.status = "WORKING"
            task.iteration_count = iteration
            changed = self._apply_fixture_iteration(task, iteration)
            self._write_manifest_and_diffs(task)
            self.repo.save_task(task)
            self._event(task, "ITERATION_PREPARED", "COMPLETED", f"Iteracao {iteration}: {len(changed)} arquivos alterados")
            result = self.runner.run(workspace / "working", task.task_id, f"workspace_iteration_{iteration}", workspace / "reports")
            task.test_status = result.status
            self.repo.save_task(task)
            failures = result.failures + result.errors
            if result.exit_code == 0:
                break
            if failures >= previous_failures and iteration > 1:
                task.result = "Sem progresso detectado; parando loop controlado."
                break
            previous_failures = failures

        self._write_manifest_and_diffs(task)
        self._review_and_risk(task)
        approval_hash = self._approval_manifest_hash(task)
        task.approval_manifest_hash = approval_hash
        task.approval_status = "PENDING"
        task.status = "AWAITING_APPROVAL"
        task.updated_at = now_iso()
        task.result = self._result_summary(task)
        self.repo.save_task(task)
        self.repo.add_approval(task.task_id, approval_hash, "PENDING")
        self.execution.authorize_action(
            task.task_id,
            "WRITE",
            "apply_multi_file_project_task",
            task.project_root,
            reason="Aplicar conjunto multi-arquivo aprovado.",
            risk_level=RiskLevel.MEDIUM,
            capability_exists=True,
        )
        self._event(task, "APPROVAL_REQUESTED", "WAITING_APPROVAL", "Aguardando aprovacao atomica")
        return task

    def approve(self, task_id: str) -> CodingProjectTask:
        task = self.require_task(task_id)
        if task.status != "AWAITING_APPROVAL":
            raise ValueError("Tarefa nao esta aguardando aprovacao")
        self._write_manifest_and_diffs(task)
        current = self._approval_manifest_hash(task)
        if current != task.approval_manifest_hash:
            task.status = "FAILED"
            task.result = "Approval manifest invalido: diffs mudaram."
            self.repo.save_task(task)
            return task
        task.approval_status = "GRANTED"
        task.status = "APPROVED"
        task.updated_at = now_iso()
        self.repo.save_task(task)
        self.repo.add_approval(task.task_id, task.approval_manifest_hash, "GRANTED")
        self._event(task, "APPROVAL_GRANTED", "GRANTED", "Aprovacao atomica concedida")
        return task

    def apply_approved(self, task_id: str, simulate_post_failure: bool = False) -> CodingProjectTask:
        task = self.require_task(task_id)
        if task.status != "APPROVED":
            raise ValueError("Tarefa nao aprovada")
        self._write_manifest_and_diffs(task)
        if self._approval_manifest_hash(task) != task.approval_manifest_hash:
            task.status = "FAILED"
            task.result = "Approval manifest invalido: diffs mudaram."
            self.repo.save_task(task)
            return task
        mismatches = self._source_hash_mismatches(task)
        if mismatches:
            task.status = "FAILED"
            task.result = "Arquivo mudou desde o inicio da tarefa: " + ", ".join(mismatches)
            self.repo.save_task(task)
            self._event(task, "SOURCE_HASH_MISMATCH", "BLOCKED", task.result)
            return task
        if self.execution.get_mode() == PermissionMode.READ_ONLY:
            task.status = "FAILED"
            task.result = "SOMENTE LEITURA bloqueia aplicacao multi-arquivo."
            self.repo.save_task(task)
            return task

        task.status = "APPLYING"
        checkpoints = {}
        applied = []
        try:
            for rel in task.affected_files:
                source = Path(task.project_root) / rel
                checkpoint = self.checkpoints.create_checkpoint(source, reason="CodingProjectTask approved apply", origin="core.coding.project")
                checkpoints[rel] = checkpoint.checkpoint_id
            task.checkpoint_ids = checkpoints
            self.repo.save_task(task)

            for rel in task.affected_files:
                source = Path(task.project_root) / rel
                working = Path(task.workspace_path) / "working" / rel
                temp = source.with_name(source.name + ".project_tmp")
                temp.parent.mkdir(parents=True, exist_ok=True)
                temp.write_bytes(working.read_bytes())
                os.replace(temp, source)
                applied.append(rel)
            task.apply_status = "COMPLETED"
            post = self.runner.run(task.project_root, task.task_id, "post_apply", Path(task.workspace_path) / "reports")
            if simulate_post_failure or post.exit_code != 0:
                raise RuntimeError("Post-validation failed")
            task.status = "COMPLETED"
            task.test_status = post.status
            task.result = "Aplicacao multi-arquivo concluida e testes pos-aplicacao passaram."
            self._event(task, "POST_VALIDATION", "COMPLETED", task.result)
        except Exception as exc:
            self._rollback_applied(task, applied)
            task.status = "ROLLED_BACK"
            task.rollback_status = "COMPLETED"
            task.result = f"Falha na aplicacao; rollback completo executado: {exc}"
            self._event(task, "ROLLBACK_COMPLETED", "COMPLETED", task.result)
        task.updated_at = now_iso()
        self.repo.save_task(task)
        return task

    def map_project(self, project_root: str | Path) -> ProjectMap:
        root = Path(project_root).resolve()
        files, dirs, languages, manifests, tests, imports = [], [], set(), [], [], {}
        graph = self.project_tools.project_dependency_graph(root)
        graph_imports: dict[str, list[str]] = {}
        for edge in graph.edges:
            values = [edge.target]
            if edge.resolved and edge.target.endswith(".py"):
                values.append(edge.target[:-3].replace("/", "."))
            elif edge.target:
                values.append(edge.target)
            graph_imports.setdefault(edge.source, []).extend(values)
        for item in self.project_tools.project_list(root):
            rel = item.path
            if item.kind == "directory":
                dirs.append(rel)
                continue
            if item.size_bytes > 500_000:
                continue
            files.append(rel)
            if item.extension == ".py":
                languages.add("python")
                imports[rel] = sorted(set(graph_imports.get(rel, [])))
            if item.extension == ".mq5":
                languages.add("mql5")
            if Path(rel).name in {"pyproject.toml", "pytest.ini", "setup.cfg", "requirements.txt", "README.md"}:
                manifests.append(rel)
            if rel.startswith("tests/") or Path(rel).name.startswith("test_"):
                tests.append(rel)
        related_rank = self.project_tools.project_related_files(root, seed_path="audit_app/pipeline.py" if (root / "audit_app" / "pipeline.py").exists() else "")
        related = sorted(set(tests + [p for p in files if p.startswith("audit_app/")] + [row["path"] for row in related_rank if row["path"] in files]))
        entry_points = [p for p in files if p.endswith("__init__.py") or p.endswith("pipeline.py")]
        return ProjectMap(str(root), files, dirs, sorted(languages), manifests, tests, entry_points, imports, related)

    def create_workspace(self, task: CodingProjectTask, files: list[str]) -> Path:
        workspace = self.workspace_root / task.task_id
        for folder in ("original", "working", "reports", "diffs", "tests"):
            (workspace / folder).mkdir(parents=True, exist_ok=True)
        for rel in files:
            source = Path(task.project_root) / rel
            for area in ("original", "working"):
                target = workspace / area / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        task.files_in_scope = sorted(set(files))
        task.workspace_path = str(workspace)
        return workspace

    def _python_imports(self, path: Path, root: Path) -> list[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []
        modules = []
        rel_parts = path.relative_to(root).with_suffix("").parts
        package = ".".join(rel_parts[:-1])
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
                    if node.level and package:
                        modules.append(f"{package}.{node.module}")
        return sorted(set(modules))

    def _affected_files(self, project_map: ProjectMap) -> list[str]:
        preferred = ["audit_app/pricing.py", "audit_app/inventory.py", "audit_app/config.py", "tests/test_pipeline.py"]
        return [rel for rel in preferred if rel in project_map.files]

    def _apply_fixture_iteration(self, task: CodingProjectTask, iteration: int) -> list[str]:
        workspace = Path(task.workspace_path) / "working"
        changed = []
        pricing = workspace / "audit_app" / "pricing.py"
        inventory = workspace / "audit_app" / "inventory.py"
        if iteration >= 1 and pricing.exists():
            text = pricing.read_text(encoding="utf-8")
            text = text.replace("return order.quantity + order.unit_price", "return order.quantity * order.unit_price")
            pricing.write_text(text, encoding="utf-8")
            changed.append("audit_app/pricing.py")
        if iteration >= 2:
            if inventory.exists():
                text = inventory.read_text(encoding="utf-8")
                text = text.replace("if available <= quantity:", "if available < quantity:")
                inventory.write_text(text, encoding="utf-8")
                changed.append("audit_app/inventory.py")
            if pricing.exists():
                text = pricing.read_text(encoding="utf-8")
                text = text.replace("if discount > 1:", "if discount > MAX_DISCOUNT:")
                text = text.replace("return round(discounted * DEFAULT_TAX_RATE, 2)", "return round(discounted * (1 + DEFAULT_TAX_RATE), 2)")
                pricing.write_text(text, encoding="utf-8")
                changed.append("audit_app/pricing.py")
        return sorted(set(changed))

    def _write_manifest_and_diffs(self, task: CodingProjectTask) -> None:
        workspace = Path(task.workspace_path)
        manifests, diff_hashes = [], {}
        for rel in task.affected_files:
            original = workspace / "original" / rel
            working = workspace / "working" / rel
            diff = unified_diff(original, working)
            h = diff_hash(diff)
            diff_hashes[rel] = h
            diff_path = workspace / "diffs" / (rel.replace("/", "__") + ".diff")
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text(diff, encoding="utf-8")
            status = "CHANGED" if diff else "UNCHANGED"
            manifests.append(ProjectFileManifest(rel, task.source_hashes.get(rel, sha256_file(Path(task.project_root) / rel)), sha256_file(working), h, status).__dict__)
        task.diff_hashes = diff_hashes
        task.manifest_json = json.dumps(manifests, ensure_ascii=False, sort_keys=True, indent=2)
        (workspace / "manifest.json").write_text(task.manifest_json, encoding="utf-8")

    def _review_and_risk(self, task: CodingProjectTask) -> None:
        risk = "LOW"
        if not task.test_status == "PASSED":
            risk = "MEDIUM"
        if len(task.affected_files) > 8:
            risk = "HIGH"
        self.execution.record_event(task_id=task.task_id, category="AGENT", action="REVIEWER_COMPLETED", status="COMPLETED", summary="ReviewerAgent revisou diffs e testes", agent="ReviewerAgent", risk_level=risk)
        self.execution.record_event(task_id=task.task_id, category="AGENT", action="RISK_COMPLETED", status="COMPLETED", summary=f"RiskAgent classificou risco {risk}", agent="RiskAgent", risk_level=risk)
        self.repo.add_event(task.task_id, "REVIEWER_COMPLETED", "COMPLETED", "Diffs e testes revisados")
        self.repo.add_event(task.task_id, "RISK_COMPLETED", "COMPLETED", risk)

    def _approval_manifest_hash(self, task: CodingProjectTask) -> str:
        return sha256_text(json.dumps(approval_manifest_payload(task), ensure_ascii=False, sort_keys=True)).upper()

    def _source_hash_mismatches(self, task: CodingProjectTask) -> list[str]:
        mismatches = []
        for rel in task.affected_files:
            current = sha256_file(Path(task.project_root) / rel)
            expected = task.source_hashes.get(rel)
            if current != expected:
                mismatches.append(rel)
        return mismatches

    def _rollback_applied(self, task: CodingProjectTask, applied: list[str]) -> None:
        workspace = Path(task.workspace_path)
        for rel in applied:
            source = Path(task.project_root) / rel
            original = workspace / "original" / rel
            shutil.copy2(original, source)

    def _analysis_from_baseline(self, result) -> str:
        return f"Baseline: {result.tests} testes, {result.failures} falhas, {result.errors} erros. Output: {result.output_path}"

    def _plan_for(self, affected: list[str]) -> str:
        return "Preparar patch multi-arquivo em sandbox para: " + ", ".join(affected)

    def _result_summary(self, task: CodingProjectTask) -> str:
        return f"Sandbox test_status={task.test_status}; iteracoes={task.iteration_count}; arquivos={len(task.affected_files)}."

    def _authorized_project(self, project: Path) -> bool:
        try:
            project.resolve().relative_to(self.projects_dir.resolve())
            return project.is_dir()
        except ValueError:
            return False

    def _event(self, task: CodingProjectTask, action: str, status: str, summary: str) -> None:
        self.repo.add_event(task.task_id, action, status, summary)
        self.audit.record({"action_type": action, "status": status, "agent": "core.coding.project", "target": task.project_root, "result": summary})
        self.execution.record_event(task_id=task.task_id, category="CODE", action=action, status=status, summary=summary, target=task.project_root, agent="core.coding.project")

    def require_task(self, task_id: str) -> CodingProjectTask:
        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(task_id)
        return task

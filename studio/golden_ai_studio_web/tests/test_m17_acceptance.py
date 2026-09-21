"""M1.7 — Acceptance test: get_project_context end-to-end."""
import shutil
import tempfile
import time
from pathlib import Path

from jarvis_core.memory.v2.engine import GoldenMemoryEngine
from jarvis_core.memory.v2.project_memory import ProjectMemoryManager


def test_acceptance():
    print("=== M1.7 ACEITACAO: get_project_context end-to-end ===\n")

    tmp = Path(tempfile.mkdtemp(prefix="aceite_"))
    db = str(tmp / "test.db")
    engine = GoldenMemoryEngine(db)
    mgr = ProjectMemoryManager(engine)

    # A) Setup projeto Golden
    print("A) Criando projeto Golden com aliases...")
    rec = mgr.create_project("Golden", aliases=["GoldenAI", "GA", "Golden Jarvis"])
    print(f"   entity_id={rec.entity_id}, name={rec.name}, aliases={rec.aliases}")

    # Registrar decisoes
    print("\nB) Registrando decisoes, issues, status...")
    mgr.record_decision("Golden", "Usar Python 3.13 como backend")
    mgr.record_decision("Golden", "Usar Tavily como research provider principal")
    mgr.record_issue("Golden", "Watcher polling tem latencia de 2s")
    mgr.record_lesson("Golden", "Nunca expor secrets em documentacao")
    mgr.record_task_completed("Golden", "M1.6.1 Segundo Cerebro concluido")
    mgr.record_status_change("Golden", "active", detail="M1.7 em andamento")
    mgr.update_project_state(
        "Golden",
        current_phase="M1.7",
        next_step="Escrever testes de aceitacao",
        important_files=["engine.py", "project_memory.py", "hybrid.py"],
    )

    # C) Nova sessao simulada (sem historico anterior)
    print("\nC) Simulando nova sessao (sem historico)...")
    del engine, mgr

    engine2 = GoldenMemoryEngine(db)
    mgr2 = ProjectMemoryManager(engine2)

    # D) Chamar get_project_context
    print('\nD) Chamando get_project_context("Golden")...')
    start = time.time()
    ctx = mgr2.get_project_context("Golden")
    elapsed = (time.time() - start) * 1000

    # E) Resultados
    print("\nE) RESULTADOS:")
    print(f"   Projeto: {ctx.project}")
    print(f"   Status: {ctx.state.status}")
    print(f"   Fase: {ctx.state.current_phase}")
    print(f"   Proximo: {ctx.state.next_step}")
    print(f"   Decisoes: {len(ctx.decisions)}")
    print(f"   Known Issues: {len(ctx.known_issues)}")
    print(f"   Handoff: {len(ctx.handoff)} chars")
    print(f"   Token estimate: {ctx.token_estimate}")
    print(f"   Tempo: {elapsed:.1f}ms")

    compact = ctx.state.to_compact()
    print(f"\n=== PROJECT STATE (compacto) ===\n{compact}")
    print(f"\nTamanho: {len(compact)} chars (max 1200)")

    print(f"\n=== HANDOFF (compacto) ===\n{ctx.handoff}")
    print(f"\nTamanho: {len(ctx.handoff)} chars (max 800)")

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n=== ACEITACAO: PASS ===")


if __name__ == "__main__":
    test_acceptance()

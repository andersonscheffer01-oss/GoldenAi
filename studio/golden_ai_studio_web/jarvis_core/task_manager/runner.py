import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from ..cancellation import CancellationToken
from .models import StepStatus, TaskStatus


class ConfirmationRequired(RuntimeError):
    def __init__(self, token):
        super().__init__("Confirmação necessária")
        self.token = token


class BackgroundJobRunner:
    def __init__(self, database, max_workers=2):
        self.database = database
        self.pool = ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 8)),
                                       thread_name_prefix="jarvis-task")
        self._tokens = {}
        self._futures = {}
        self._lock = threading.RLock()

    def submit(self, task_id, executor):
        with self._lock:
            if task_id in self._futures and not self._futures[task_id].done():
                raise RuntimeError("Tarefa já está em execução.")
            token = CancellationToken()
            self._tokens[task_id] = token
            future = self.pool.submit(self._run, task_id, executor, token)
            self._futures[task_id] = future
            return future

    def cancel(self, task_id):
        with self._lock:
            task = self.database.get_task(task_id)
            if not task or task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                return False
            future = self._futures.get(task_id)
            if task.status in {TaskStatus.QUEUED, TaskStatus.INTERRUPTED} and not future:
                self._cancel_remaining(task_id, self.database.get_steps(task_id))
                self.database.update_task(task_id, TaskStatus.CANCELLED,
                    cancel_requested_at=time.time(), finished_at=time.time())
                return True
            token = self._tokens.get(task_id)
            if token:
                token.request_cancel()
            self.database.update_task(task_id, TaskStatus.CANCEL_REQUESTED,
                                      cancel_requested_at=time.time())
            return True

    def future(self, task_id):
        with self._lock:
            return self._futures.get(task_id)

    def shutdown(self, wait=True):
        self.pool.shutdown(wait=wait, cancel_futures=True)

    def _run(self, task_id, executor, token):
        task = self.database.get_task(task_id)
        if not task:
            return None
        self.database.update_task(task_id, TaskStatus.RUNNING, started_at=time.time())
        deadline = time.monotonic() + task.timeout_seconds
        all_steps = self.database.get_steps(task_id)
        completed = {item.step.id for item in all_steps if item.status == StepStatus.COMPLETED}
        results = {item.step.id: item.result for item in all_steps if item.status == StepStatus.COMPLETED}
        try:
            remaining = [item for item in all_steps if item.status != StepStatus.COMPLETED]
            while remaining:
                if token.is_cancelled():
                    self._cancel_remaining(task_id, remaining)
                    self.database.update_task(task_id, TaskStatus.CANCELLED, finished_at=time.time())
                    return self.database.get_task(task_id)
                ready = [item for item in remaining if set(item.step.dependencies) <= completed]
                if not ready:
                    raise RuntimeError("Nenhuma etapa liberada; dependências não resolvidas.")
                item = ready[0]
                self.database.update_step(task_id, item.step.id, StepStatus.RUNNING,
                                          started_at=time.time())
                remaining_timeout = deadline - time.monotonic()
                if remaining_timeout <= 0:
                    raise TimeoutError()
                result = self._execute_step(executor, item.step, token, remaining_timeout)
                if isinstance(result, dict) and result.get("response_policy"):
                    if not result.get("success"):
                        raise RuntimeError(result.get("error") or "Etapa falhou.")
                    if not result.get("verified"):
                        raise RuntimeError("Etapa executada sem confirmação da pós-condição.")
                if token.is_cancelled() and item.step.cancellable:
                    self.database.update_step(task_id, item.step.id, StepStatus.CANCELLED,
                                              finished_at=time.time())
                    remaining.remove(item)
                    self._cancel_remaining(task_id, remaining)
                    self.database.update_task(task_id, TaskStatus.CANCELLED, finished_at=time.time())
                    return self.database.get_task(task_id)
                self.database.update_step(task_id, item.step.id, StepStatus.COMPLETED,
                                          result=result, finished_at=time.time())
                completed.add(item.step.id)
                results[item.step.id] = result
                remaining.remove(item)
            self.database.update_task(task_id, TaskStatus.COMPLETED, result=results,
                                      finished_at=time.time())
        except TimeoutError:
            token.request_cancel()
            self._fail_running(task_id, "Timeout da tarefa excedido.")
        except ConfirmationRequired as exc:
            for item in self.database.get_steps(task_id):
                if item.status == StepStatus.RUNNING:
                    self.database.update_step(task_id, item.step.id, StepStatus.WAITING_CONFIRMATION,
                                              result={"confirmation_token": exc.token})
            self.database.update_task(task_id, TaskStatus.WAITING_CONFIRMATION,
                                      result={"confirmation_token": exc.token})
        except Exception as exc:
            self._fail_running(task_id, str(exc))
        return self.database.get_task(task_id)

    @staticmethod
    def _execute_step(executor, step, token, timeout):
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-step")
        future = pool.submit(executor, step, token)
        try:
            return future.result(timeout=timeout)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _cancel_remaining(self, task_id, items):
        for item in items:
            self.database.update_step(task_id, item.step.id, StepStatus.CANCELLED,
                                      finished_at=time.time())

    def _fail_running(self, task_id, error):
        for item in self.database.get_steps(task_id):
            if item.status == StepStatus.RUNNING:
                self.database.update_step(task_id, item.step.id, StepStatus.FAILED,
                                          error=error[:1000], finished_at=time.time())
            elif item.status == StepStatus.PENDING:
                self.database.update_step(task_id, item.step.id, StepStatus.BLOCKED,
                                          error="Etapa anterior falhou")
        self.database.update_task(task_id, TaskStatus.FAILED, error=error[:1000],
                                  finished_at=time.time())

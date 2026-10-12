from hub.queue import JobQueue
from hub.workspace import WorkspaceManager
from hub.runners import MODULE_RUNNERS
from hub.worker import CoreWorker
from hub.service import JobService
from publisher.publisher import Publisher

# Hub シングルトンインスタンス
job_queue = JobQueue()
workspace_manager = WorkspaceManager()
publisher = Publisher()
core_worker = CoreWorker(
    job_queue=job_queue,
    workspace_manager=workspace_manager,
    publisher=publisher,
    module_runners=MODULE_RUNNERS,
)
job_service = JobService(
    job_queue=job_queue,
    workspace_manager=workspace_manager,
    core_worker=core_worker,
)

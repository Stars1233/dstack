from pathlib import Path
from typing import List, Union
from uuid import UUID

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.logs import (
    JobSubmissionLogs,
    LogEvent,
    LogEventSource,
    LogProducer,
)
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.base import (
    LogStorage,
    unix_time_ms_to_datetime,
)


class FileLogStorage(LogStorage):
    root: Path

    def __init__(self, root: Union[Path, str, None] = None) -> None:
        if root is None:
            self.root = settings.SERVER_DIR_PATH
        else:
            self.root = Path(root)

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        log_producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        log_file_path = self._get_log_file_path(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
            producer=log_producer,
        )

        start_line = 0
        if request.next_token:
            try:
                start_line = int(request.next_token)
                if start_line < 0:
                    raise ServerClientError(
                        f"Invalid next_token: {request.next_token}. Must be a non-negative integer."
                    )
            except ValueError:
                raise ServerClientError(
                    f"Invalid next_token: {request.next_token}. Must be a valid integer."
                )

        logs = []
        next_token = None
        current_line = 0

        try:
            with open(log_file_path) as f:
                # Skip to start_line if needed
                for _ in range(start_line):
                    if f.readline() == "":
                        # File is shorter than start_line
                        return JobSubmissionLogs(logs=logs, next_token=next_token)
                    current_line += 1

                # Read lines one by one
                while True:
                    line = f.readline()
                    if line == "":  # EOF
                        break

                    current_line += 1

                    try:
                        log_event = LogEvent.__response__.parse_raw(line)
                    except Exception:
                        # Skip malformed lines
                        continue

                    if request.start_time and log_event.timestamp <= request.start_time:
                        continue
                    if request.end_time is not None and log_event.timestamp >= request.end_time:
                        break

                    logs.append(log_event)

                    if len(logs) >= request.limit:
                        # Check if there are more lines to read
                        if f.readline() != "":
                            next_token = str(current_line)
                        break
        except FileNotFoundError:
            pass

        return JobSubmissionLogs(logs=logs, next_token=next_token)

    def write_logs(
        self,
        project: ProjectModel,
        run_name: str,
        job_submission_id: UUID,
        runner_logs: List[RunnerLogEvent],
        job_logs: List[RunnerLogEvent],
    ):
        if len(runner_logs) > 0:
            runner_log_file_path = self._get_log_file_path(
                project.name, run_name, job_submission_id, LogProducer.RUNNER
            )
            self._write_logs(
                log_file_path=runner_log_file_path,
                log_events=runner_logs,
            )
        if len(job_logs) > 0:
            job_log_file_path = self._get_log_file_path(
                project.name, run_name, job_submission_id, LogProducer.JOB
            )
            self._write_logs(
                log_file_path=job_log_file_path,
                log_events=job_logs,
            )

    def _write_logs(self, log_file_path: Path, log_events: List[RunnerLogEvent]) -> None:
        log_events_parsed = [self._runner_log_event_to_log_event(event) for event in log_events]
        log_file_path.parent.mkdir(exist_ok=True, parents=True)
        with open(log_file_path, "a") as f:
            f.writelines(log.json() + "\n" for log in log_events_parsed)

    def _get_log_file_path(
        self,
        project_name: str,
        run_name: str,
        job_submission_id: UUID,
        producer: LogProducer,
    ) -> Path:
        return (
            self.root
            / "projects"
            / project_name
            / "logs"
            / run_name
            / str(job_submission_id)
            / f"{producer.value}.log"
        )

    def _runner_log_event_to_log_event(self, runner_log_event: RunnerLogEvent) -> LogEvent:
        return LogEvent(
            timestamp=unix_time_ms_to_datetime(runner_log_event.timestamp),
            log_source=LogEventSource.STDOUT,
            message=runner_log_event.message.decode(errors="replace"),
        )

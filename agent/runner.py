import asyncio
import json
import logging
import tempfile
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)


class OpenCodeError(Exception):
    pass


async def run_opencode(
    repo_name: str,
    prompt: str,
    timeout: int = 1800,    # 30 min default — implementation can be slow
) -> str:
    """
    Invoke OpenCode headlessly in the given repo directory.
    Returns the agent's final text output.
    Raises OpenCodeError on non-zero exit or empty output.
    """
    repo_path = settings.repo_path(repo_name)

    if not repo_path.exists():
        raise OpenCodeError(f"Repo path does not exist: {repo_path}")

    # Write prompt to a temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        prefix=f"speckit-prompt-",
    ) as f:
        f.write(prompt)
        prompt_file = Path(f.name)

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c",
            f"cd {repo_path} && opencode run "
            f"--model {settings.opencode_model} "
            f"--dangerously-skip-permissions "
            f"--format json "
            f"--print-logs "
            f"--log-level INFO "
            f'"$(cat {prompt_file})"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        prompt_preview = prompt[:200].replace("\n", "\\n")
        logger.info(f"Running OpenCode in {repo_path} (timeout: {timeout}s)")
        logger.debug("Prompt [first 200 chars]: %s", prompt_preview)

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise OpenCodeError(f"OpenCode timed out after {timeout}s")

        stdout_str = stdout.decode()
        stderr_str = stderr.decode()

        logger.debug("OpenCode stdout (first 5000 chars): %s", stdout_str[:5000])

        if proc.returncode != 0:
            # Extract error from JSON events in stdout (OpenCode outputs errors to stdout with --format json)
            error_detail = stderr_str or _extract_json_error(stdout_str)
            raise OpenCodeError(
                f"OpenCode exited with code {proc.returncode}: {error_detail}"
            )

        return _parse_output(stdout_str)

    finally:
        prompt_file.unlink(missing_ok=True)


def _extract_json_error(stdout: str) -> str:
    """Extract error message from OpenCode's JSON event stream in stdout."""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "error":
            err = event.get("error", {})
            return json.dumps(err.get("data", err), indent=2)
        # Also capture assistant error blocks
        if event.get("role") == "assistant":
            for block in event.get("content", []):
                if block.get("type") == "error":
                    return json.dumps(block, indent=2)
    return stdout[:2000]


def _parse_output(stdout: str) -> str:
    """
    Extract the model's text output from OpenCode's JSON event stream.
    Falls back to raw stdout if parsing fails.
    """
    texts: list[str] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "text":
            part = event.get("part", {})
            text = part.get("text", "")
            if text:
                texts.append(text)

    if not texts:
        logger.warning("No text events found in OpenCode output — returning raw stdout")
        return stdout

    return "\n".join(texts)

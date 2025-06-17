"""Multi-user enhanced Docker runtime with user isolation."""

import os
from pathlib import Path
from typing import Callable

from openhands.core.config import OpenHandsConfig
from openhands.events import EventStream
from openhands.integrations.provider import PROVIDER_TOKEN_TYPE
from openhands.runtime.impl.docker.docker_runtime import DockerRuntime
from openhands.runtime.plugins import PluginRequirement
from openhands.runtime.utils.command import DEFAULT_MAIN_MODULE


class MultiUserDockerRuntime(DockerRuntime):
    """Enhanced Docker runtime with multi-user isolation support.

    This extends the standard DockerRuntime to provide proper user isolation:
    - User-specific container naming
    - User-scoped workspace mounting
    - User-specific environment variables
    - User-based resource limits
    """

    def __init__(
        self,
        config: OpenHandsConfig,
        event_stream: EventStream,
        sid: str = 'default',
        plugins: list[PluginRequirement] | None = None,
        env_vars: dict[str, str] | None = None,
        status_callback: Callable | None = None,
        attach_to_existing: bool = False,
        headless_mode: bool = True,
        user_id: str | None = None,
        git_provider_tokens: PROVIDER_TOKEN_TYPE | None = None,
        main_module: str = DEFAULT_MAIN_MODULE,
    ):
        # Store user_id for use in container management
        self.user_id = user_id

        # Call parent constructor
        super().__init__(
            config,
            event_stream,
            sid,
            plugins,
            env_vars,
            status_callback,
            attach_to_existing,
            headless_mode,
            user_id,
            git_provider_tokens,
            main_module,
        )

        # Override container name to include user_id for isolation
        if self.user_id:
            # Format: openhands-runtime-{user_id}-{session_id}
            self.container_name = f'openhands-runtime-{self.user_id}-{sid}'
        else:
            # Fallback to original naming
            self.container_name = f'openhands-runtime-{sid}'

    def _process_volumes(self) -> dict[str, dict[str, str]]:
        """Process volume mounts with user isolation."""
        volumes = super()._process_volumes()

        # If user_id is provided, create user-specific workspace
        if self.user_id and not volumes:
            # Create user-specific workspace directory
            user_workspace_base = '/tmp/openhands/workspaces'
            user_workspace = os.path.join(user_workspace_base, self.user_id)

            # Ensure user workspace directory exists
            Path(user_workspace).mkdir(parents=True, exist_ok=True)

            # Mount user-specific workspace
            volumes[user_workspace] = {
                'bind': '/workspace',
                'mode': 'rw',
            }

            self.log(
                'debug',
                f'Using user-specific workspace: {user_workspace} -> /workspace',
            )

        # If user has existing volumes configured, ensure they're user-scoped
        elif self.user_id and volumes:
            # Update volume paths to be user-specific if they're not already
            updated_volumes = {}
            for host_path, mount_config in volumes.items():
                # If the path doesn't already include user_id, make it user-specific
                if self.user_id not in host_path and not os.path.isabs(host_path):
                    user_workspace_base = '/tmp/openhands/workspaces'
                    user_host_path = os.path.join(
                        user_workspace_base, self.user_id, host_path
                    )
                    Path(user_host_path).mkdir(parents=True, exist_ok=True)
                    updated_volumes[user_host_path] = mount_config

                    self.log(
                        'debug',
                        f'Updated volume to be user-specific: {host_path} -> {user_host_path}',
                    )
                else:
                    updated_volumes[host_path] = mount_config

            volumes = updated_volumes

        return volumes

    def init_container(self) -> None:
        """Initialize container with user-specific configuration."""
        # Add user-specific environment variables
        if self.user_id:
            if not hasattr(self, 'initial_env_vars'):
                self.initial_env_vars = {}

            # Add user ID to environment
            self.initial_env_vars.update(
                {
                    'OPENHANDS_USER_ID': self.user_id,
                    'USER_WORKSPACE': '/workspace',
                }
            )

            self.log(
                'debug',
                f'Added user-specific environment variables for user: {self.user_id}',
            )

        # Call parent init_container
        super().init_container()

    def get_user_workspace_path(self) -> str:
        """Get the user-specific workspace path on the host."""
        if self.user_id:
            user_workspace_base = '/tmp/openhands/workspaces'
            return os.path.join(user_workspace_base, self.user_id)
        else:
            return '/tmp/openhands/workspace'

    def get_container_workspace_path(self) -> str:
        """Get the workspace path inside the container."""
        return '/workspace'

    @classmethod
    async def delete(cls, conversation_id: str, user_id: str | None = None) -> None:
        """Delete container with user-specific naming."""
        docker_client = cls._init_docker_client()
        try:
            if user_id:
                container_name = f'openhands-runtime-{user_id}-{conversation_id}'
            else:
                container_name = f'openhands-runtime-{conversation_id}'

            container = docker_client.containers.get(container_name)
            container.remove(force=True)
        except Exception:
            # Container doesn't exist or other error - ignore
            pass
        finally:
            docker_client.close()

    def pause(self) -> None:
        """Pause the runtime with user context preservation."""
        if not self.container:
            raise RuntimeError('Container not initialized')

        self.log('debug', f'Pausing container for user: {self.user_id or "unknown"}')
        super().pause()

    def resume(self) -> None:
        """Resume the runtime with user context preservation."""
        if not self.container:
            raise RuntimeError('Container not initialized')

        self.log('debug', f'Resuming container for user: {self.user_id or "unknown"}')
        super().resume()

    def close(self, rm_all_containers: bool | None = None) -> None:
        """Close runtime with user-specific cleanup."""
        self.log('debug', f'Closing runtime for user: {self.user_id or "unknown"}')
        super().close(rm_all_containers)


def create_user_runtime(
    config: OpenHandsConfig,
    event_stream: EventStream,
    sid: str,
    user_id: str | None = None,
    **kwargs,
) -> MultiUserDockerRuntime:
    """Factory function to create a user-specific Docker runtime."""
    return MultiUserDockerRuntime(
        config=config, event_stream=event_stream, sid=sid, user_id=user_id, **kwargs
    )

#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Handy Python utilities for this project
"""

from __future__ import annotations

import os

from .internal_types import *
from .pkg_logging import logger

from .util import (
    docker_compose_call,
    docker_compose_call_output,
  )

class DockerComposeStack:
    """
    An object-oriented interface and context manager for a docker-compose
    stack that can be brought up and down during a context lifetime.
    """
    env: Dict[str, str]
    """The environment variables to use when calling docker-compose"""

    cwd: Optional[str]
    """The current working directory to use when calling docker-compose"""

    options: List[str]
    """The options to pass to docker-compose for all commands"""

    up_options: List[str]
    """The options to pass to docker-compose for the "up" command"""

    down_options: List[str]
    """The options to pass to docker-compose for the "down" command"""

    auto_down_on_enter: bool
    """Whether to automatically call "down" when the context is entered. If combined with auto_up,
       the stack is brought down, then up again"""

    auto_up: bool
    """Whether to automatically call "up" when the context is entered. If combined with auto_down_on_enter,
       the stack is brought down, then up again"""


    auto_down: bool
    """Whether to automatically call "down" when the context is exited"""

    project_dir: str
    """The primary directory in which docker-compose is evaluated.
       Defaults to the directory containing the first listed compose file,
       or cwd if no files are listed."""

    project_name: str
    """The name of the docker-compose project. Defaults to the basename of the project directory"""

    docker_compose_files: List[str]
    """The absolute paths of the docker-compose files used by the stack"""

    name: str
    """A friendly name of the stack, for logging purposes"""

    up_stderr_exception: bool
    """Whether to capture stderr and include in exception when the context is entered."""


    def __init__(
            self,
            compose_file: Optional[Union[str, List[str]]]=None,
            *,
            options: Optional[List[str]]=None,
            env_file: Optional[Union[str, List[str]]]=None,
            parallel: Optional[int]=None,
            profile: Optional[Union[str, List[str]]]=None,
            progress: Optional[str]=None,
            project_directory: Optional[str]=None,
            project_name: Optional[str]=None,
            name: Optional[str]=None,
            auto_down_on_enter: bool=False,
            auto_up: bool=True,
            auto_down: bool=False,
            up_options: Optional[List[str]]=None,
            down_options: Optional[List[str]]=None,
            build: bool=False,
            no_build: bool=False,
            always_recreate_deps: bool=False,
            force_recreate: bool=False,
            no_deps: bool=False,
            no_log_prefix: bool=False,
            no_recreate: bool=False,
            no_start: bool=False,
            pull: Optional[str]=None,
            quiet_pull: bool=False,
            remove_orphans: bool=True,
            renew_anon_volumes: bool=False,
            timeout: Optional[int]=None,
            timestamps: bool=False,
            wait: bool = False,
            wait_timeout: Optional[int]=None,
            remove_local_images: bool=False,
            remove_all_images: bool=False,
            env: Optional[Mapping[str, str]]=None,
            additional_env: Optional[Mapping[str, str]]=None,
            cwd: Optional[str]=None,
            up_stderr_exception: bool=False,
          ):
        """
        Create a DockerComposeStack instance, which provides
        a configuration and context for a docker-compose stack
        in which docker-compose commands/operations can be executed.

        Args:
            compose_file:
                The docker-compose file(s) to use. If a string, it is
                the path to a single docker-compose file. If a list of strings,
                each string is the path to a docker-compose file. By default,
                the docker-compose.yml file in the working directory directory is used.

            options:
                Additional command-line options to pass to docker-compose for all commands.

            env_file:
                One or more path(s) to environment file(s) to use when calling docker-compose.

            parallel:
                The number of containers to start in parallel. Defaults to 1.

            profile:
                The name of one or more profiles to use when calling docker-compose.

            progress:
                Set type of progress output (auto, plain, tty). Defaults to "auto".

            project_directory:
                The directory in which docker-compose is evaluated. Defaults to
                the directory containing the first evaluated compose file

            project_name:
                The name of the docker-compose project. Defaults to the basename of the
                docker-compose project directory.

            name:
                A friendly name of the stack, for logging purposes. Defaults to the project name.

            auto_down_on_enter:
                Whether to bring the stack down before bringing it up when the context is entered.
                If combined with auto_up, the stack is brought down, then up again.

            auto_up:
                Whether to automatically bring the stack up when the context is entered.
                If combined with auto_down_on_enter, the stack is brought down, then up again.

            auto_down:
                Whether to automatically bring the stack down when the context is exited.

            up_options:
                Additional command-line options to pass to docker-compose for the "up" command.

            down_options:
                Additional command-line options to pass to docker-compose for the "down" command.

            build:
                Build images before starting containers. Defaults to False.

            no_build:
                Don't build images before starting containers. Defaults to False.

            always_recreate_deps:
                Recreate dependent containers. Defaults to False.

            force_recreate:
                Recreate containers even if their configuration and image haven't changed.
                Defaults to False.

            no_deps:
                Don't start linked services. Defaults to False.

            no_log_prefix:
                Don't print prefix in logs. Defaults to False.

            no_recreate:
                If containers already exist, don't recreate them. Defaults to False.

            no_start:
                Don't start containers after creating them. Defaults to False.

            pull:
                Pull image before running ("always"|"missing"|"never"). Defaults to "missing"

            quiet_pull:
                Pull without printing progress information. Defaults to False.

            remove_orphans:
                Remove containers for services not defined in the Compose file. Defaults to True.

            renew_anon_volumes:
                Recreate anonymous volumes instead of retrieving data from the previous containers.
                Defaults to False.

            timeout:
                Use this timeout in seconds for container shutdown when attached or when containers
                are already running. Defaults to 10.

            timestamps:
                Show timestamps. Defaults to False.

            wait:
                Wait for services to be running/healthy on up. Defaults to False.

            wait_timeout:
                Timeout waiting for services to be running/healthy. Defaults to 10.

            remove_local_images:
                On down, remove local images used by an service that
                don't have a custom tag.

            remove_all_images:
                On down, remove all images used by any service.

            env:
                The base environment in which to run docker-compose. Must include the operating
                environment (search PATH, etc). Defaults to os.environ.

            additional_env:
                Additional environment variables to set when running docker-compose. Variables
                in this dictionary override those in the base environment.

            cwd:
                The current working directory to use when running docker-compose. Defaults to
                the current working directory at the time the command is invoked.

            up_stderr_exception:
                Whether to capture stderr and include in exception when the context is entered.
                By default, stderr is not captured and is printed to the console.
        """
        self.auto_down_on_enter = auto_down_on_enter
        self.auto_up = auto_up
        self.auto_down = auto_down
        self.up_stderr_exception = up_stderr_exception
        if cwd is not None:
            cwd = os.path.abspath(os.path.normpath(cwd))
        self.options = []
        if options is not None:
            self.options.extend(options)
        if env_file is not None:
            if isinstance(env_file, str):
                self.options.extend(["--env-file", env_file])
            else:
                assert isinstance(env_file, list)
                for env_filename in env_file:
                    assert isinstance(env_filename, str)
                    self.options.extend(["--env-file", env_filename])
        if parallel is not None:
            self.options.extend(["--parallel", str(parallel)])
        if profile is not None:
            if isinstance(profile, str):
                self.options.extend(["--profile", profile])
            else:
                assert isinstance(profile, list)
                for profile_name in profile:
                    assert isinstance(profile_name, str)
                    self.options.extend(["--profile", profile_name])
        if progress is not None:
            self.options.extend(["--progress", progress])
        if project_directory is not None:
            self.options.extend(["--project-directory", project_directory])
        if project_name is not None:
            self.options.extend(["--project-name", project_name])
        self.up_options = [ "-d" ]
        if up_options is not None:
            self.up_options.extend(up_options)
        self.down_options = []
        if down_options is not None:
            self.down_options.extend(down_options)
        compose_files: List[str] = []
        if compose_file is not None:
            if isinstance(compose_file, str):
                compose_files.append(compose_file)
            else:
                assert isinstance(compose_file, list)
                for file in compose_file:
                    assert isinstance(file, str)
                    compose_files.append(file)
        for compose_file_name in compose_files:
            self.options.extend(["-f", compose_file_name])
        option_pairs: List[Tuple[str, str]] = []
        i = 0
        while i < len(self.options):
            if self.options[i] .startswith("-"):
                option = self.options[i]
                i += 1
                has_value_arg: bool = False
                option_name: str = ""
                option_value: str = ""
                if option.startswith("--"):
                    if "=" in option:
                        option_name, option_value = option.split('=', 1)
                        option_pairs.append((option_name, option_value))
                    else:
                        option_name = option
                        has_value_arg = option_name in [
                            "--ansi", "--env-file", "--file", "--parallel", "--profile",
                            "--progress","--project-directory", "--project-name"]
                else:
                    for i_opt_ch, opt_ch in enumerate(option[1:]):
                        option_name = "-" + opt_ch
                        has_value_arg = option_name in ["-f", "-p"]
                        if has_value_arg:
                            if i_opt_ch < len(option) - 2:
                                raise HubError(f"Option {option_name} must be last in a group of options")
                            break
                        option_pairs.append((option_name, ""))
                if has_value_arg:
                    if i >= len(self.options):
                        raise HubError(f"Missing option value after {option_name}")
                    option_value = self.options[i]
                    i += 1
                    option_pairs.append((option_name, option_value))
        logger.debug(f"DockerComposeStack: option_pairs: {option_pairs}")
        project_directory = None
        project_name = None
        docker_compose_files: List[str] = []
        for option_name, option_value in option_pairs:
            if option_name in ("-f", "--file"):
                docker_compose_files.append(option_value)
            elif option_name == "--project-directory":
                project_directory = option_value
            elif option_name in ("-p", "--project-name"):
                project_name = option_value
        if project_directory is None:
            if len(docker_compose_files) > 0:
                project_directory = os.path.dirname(docker_compose_files[0])
        if project_directory is None:
                project_directory = "."
        base_dir = os.getcwd() if cwd is None else os.path.abspath(os.path.normpath(cwd))
        project_directory = os.path.abspath(os.path.join(base_dir, os.path.normpath(project_directory)))
        self.project_directory = project_directory
        if len(docker_compose_files) == 0:
            docker_compose_files.append(os.path.join(project_directory, "docker-compose.yml"))
        self.docker_compose_files = docker_compose_files
        if project_name is None:
            project_name = os.path.basename(project_directory)
        self.project_name = project_name

        if name is None:
            name = project_name
        self.name = name

        if build:
            self.up_options.append("--build")
        if no_build:
            self.up_options.append("--no-build")
        if always_recreate_deps:
            self.up_options.append("--always-recreate-deps")
        if force_recreate:
            self.up_options.append("--force-recreate")
        if no_deps:
            self.up_options.append("--no-deps")
        if no_log_prefix:
            self.up_options.append("--no-log-prefix")
        if no_recreate:
            self.up_options.append("--no-recreate")
        if no_start:
            self.up_options.append("--no-start")
        if pull is not None:
            self.up_options.append(f"--pull={pull}")
        if quiet_pull:
            self.up_options.append("--quiet-pull")
        if remove_orphans:
            self.up_options.append("--remove-orphans")
            self.down_options.append("--remove-orphans")
        if renew_anon_volumes:
            self.up_options.append("--renew-anon-volumes")
        if timeout is not None:
            self.up_options.append(f"--timeout={timeout}")
        if timestamps:
            self.up_options.append("--timestamps")
        if wait:
            self.up_options.append(f"--wait={wait}")
        if wait_timeout is not None:
            self.up_options.append(f"--wait-timeout={wait_timeout}")
        if remove_all_images:
            self.down_options.append("--rmi=all")
        elif remove_local_images:
            self.down_options.append("--rmi=local")

        self.env = dict(os.environ if env is None else env)
        if additional_env is not None:
            self.env.update(additional_env)
        self.cwd = cwd

    def call(
            self,
            args: List[str],
            *,
            stderr_exception: bool=False,
          ) -> None:
        """
        Call docker-compose with the stack options and the given arguments.
        Automatically uses sudo if login session is not yet in the "docker" group.
        If an error occurs, stderr output is printed and an exception is raised.
        """
        docker_compose_call(
            self.options + args,
            env=self.env,
            cwd=self.cwd,
            stderr_exception=stderr_exception,
          )
        
    def call_output(
            self,
            args: List[str],
            *,
            stderr_exception: bool=True,
          ) -> str:
        """
        Call docker-compose with the stack options and the given arguments and return the stdout text
        Automatically uses sudo if login session is not yet in the "docker" group.
        If an error occurs, stderr output is printed and an exception is raised.
        """
        return docker_compose_call_output(
            self.options + args,
            env=self.env,
            cwd=self.cwd,
            stderr_exception=stderr_exception,
          )

    def up(self, stderr_exception: bool=False) -> None:
        """
        Start the stack
        """
        self.call(["up"] + self.up_options, stderr_exception=stderr_exception)
        
    def down(self) -> None:
        """
        Stop the stack
        """
        self.call(["down"] + self.down_options)

    def logs(self, options: Optional[List[str]]=None) -> None:
        """
        Display the logs for the stack
        """
        options = [] if options is None else options
        self.call(["logs"] + options)

    def ps(self, options: Optional[List[str]]=None) -> None:
        """
        Display the docker containers associated with the stack
        """
        options = [] if options is None else options
        self.call(["ps"] + options)

    def has_running_containers(self) -> bool:
        """
        Return True if the stack has any running containers
        """
        text = self.call_output(["ps", "-q"])
        return text.rstrip() != ""

    def __enter__(self) -> DockerComposeStack:
        """Enters a context for the stack, bringing it down if auto_down_on_enter is True,
           then bringing it up if auto_up is True.
        """
        try:
            if self.auto_down_on_enter:
                self.down()
            if self.auto_up:
                self.up(stderr_exception=self.up_stderr_exception)
        except BaseException as e:
            if self.auto_up:
                logger.debug("Failed to start docker-compose stack; tearing down")
                self.down()
            raise
        return self
    
    def __exit__(
            self,
            exc_type: type[BaseException],
            exc_val: Optional[BaseException],
            exc_tb: TracebackType
          ) -> None:
        """Exits a context for the stack, bringing it down if auto_down is True"""
        if self.auto_down:
            self.down()


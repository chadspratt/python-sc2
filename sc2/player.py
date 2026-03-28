# pyre-ignore-all-errors[6, 11, 16, 29]
from __future__ import annotations

from abc import ABC
from pathlib import Path

from sc2.bot_ai import BotAI
from sc2.data import AIBuild, Difficulty, PlayerType, Race

from s2clientprotocol import sc2api_pb2


class AbstractPlayer(ABC):
    def __init__(
        self,
        p_type: PlayerType,
        race: Race | None = None,
        name: str | None = None,
        difficulty: Difficulty | None = None,
        ai_build: AIBuild | None = None,
        fullscreen: bool = False,
    ) -> None:
        assert isinstance(p_type, PlayerType), f"p_type is of type {type(p_type)}"
        assert name is None or isinstance(name, str), f"name is of type {type(name)}"

        self.name = name
        self.type = p_type
        self.fullscreen = fullscreen
        if race is not None:
            self.race = race
        if p_type == PlayerType.Computer:
            assert isinstance(difficulty, Difficulty), f"difficulty is of type {type(difficulty)}"
            # Workaround, proto information does not carry ai_build info
            # We cant set that in the Player classmethod
            assert ai_build is None or isinstance(ai_build, AIBuild), f"ai_build is of type {type(ai_build)}"
            self.difficulty = difficulty
            self.ai_build = ai_build

        elif p_type == PlayerType.Observer:
            assert race is None
            assert difficulty is None
            assert ai_build is None

        else:
            assert isinstance(race, Race), f"race is of type {type(race)}"
            assert difficulty is None
            assert ai_build is None

    @property
    def needs_sc2(self) -> bool:
        return not isinstance(self, Computer)


class Human(AbstractPlayer):
    def __init__(self, race: Race, name: str | None = None, fullscreen: bool = False) -> None:
        super().__init__(PlayerType.Participant, race, name=name, fullscreen=fullscreen)

    def __str__(self) -> str:
        if self.name is not None:
            return f"Human({self.race._name_}, name={self.name!r})"
        return f"Human({self.race._name_})"


class Bot(AbstractPlayer):
    def __init__(self, race: Race, ai: BotAI, name: str | None = None, fullscreen: bool = False) -> None:
        """
        AI can be None if this player object is just used to inform the
        server about player types.
        """
        assert isinstance(ai, BotAI) or ai is None, f"ai is of type {type(ai)}, inherit BotAI from bot_ai.py"
        super().__init__(PlayerType.Participant, race, name=name, fullscreen=fullscreen)
        self.ai = ai

    def __str__(self) -> str:
        if self.name is not None:
            return f"Bot {self.ai.__class__.__name__}({self.race._name_}), name={self.name!r})"
        return f"Bot {self.ai.__class__.__name__}({self.race._name_})"


class Computer(AbstractPlayer):
    def __init__(
        self, race: Race, difficulty: Difficulty = Difficulty.Easy, ai_build: AIBuild = AIBuild.RandomBuild
    ) -> None:
        super().__init__(PlayerType.Computer, race, difficulty=difficulty, ai_build=ai_build)

    def __str__(self) -> str:
        return f"Computer {self.difficulty._name_}({self.race._name_}, {self.ai_build.name})"


class Observer(AbstractPlayer):
    def __init__(self) -> None:
        super().__init__(PlayerType.Observer)

    def __str__(self) -> str:
        return "Observer"


class Player(AbstractPlayer):
    def __init__(
        self,
        player_id: int,
        p_type: PlayerType,
        requested_race: Race,
        difficulty: Difficulty | None = None,
        actual_race: Race | None = None,
        name: str | None = None,
        ai_build: AIBuild | None = None,
    ) -> None:
        super().__init__(p_type, requested_race, difficulty=difficulty, name=name, ai_build=ai_build)
        self.id: int = player_id
        self.actual_race: Race | None = actual_race

    @classmethod
    def from_proto(cls, proto: sc2api_pb2.PlayerInfo) -> Player:
        if PlayerType(proto.type) == PlayerType.Observer:
            return cls(proto.player_id, PlayerType(proto.type), None, None, None)
        return cls(
            proto.player_id,
            PlayerType(proto.type),
            Race(proto.race_requested),
            Difficulty(proto.difficulty) if proto.HasField("difficulty") else None,
            Race(proto.race_actual) if proto.HasField("race_actual") else None,
            proto.player_name if proto.HasField("player_name") else None,
        )


class BotProcess(AbstractPlayer):
    """
    Class for handling bots launched externally, including non-python bots.
    Default parameters comply with sc2ai and aiarena ladders.

    :param path: the executable file's path
    :param launch_list: list of strings that launches the bot e.g. ["python", "run.py"] or ["run.exe"]
    :param race: bot's race
    :param name: bot's name
    :param sc2port_arg: the accepted argument name for the port of the sc2 instance to listen to
    :param hostaddress_arg: the accepted argument name for the address of the sc2 instance to listen to
    :param match_arg: the accepted argument name for the starting port to generate a portconfig from
    :param realtime_arg: the accepted argument name for specifying realtime
    :param other_args: anything else that is needed

    e.g. to call a bot capable of running on the bot ladders:
        BotProcess(os.getcwd(), "python run.py", Race.Terran, "INnoVation")
    """

    def __init__(
        self,
        path: str | Path,
        launch_list: list[str],
        race: Race,
        name: str | None = None,
        sc2port_arg: str = "--GamePort",
        hostaddress_arg: str = "--LadderServer",
        match_arg: str = "--StartPort",
        realtime_arg: str = "--RealTime",
        other_args: str | None = None,
        stdout: str | None = None,
    ) -> None:
        super().__init__(PlayerType.Participant, race, name=name)
        assert Path(path).exists()
        self.path = path
        self.launch_list = launch_list
        self.sc2port_arg = sc2port_arg
        self.match_arg = match_arg
        self.hostaddress_arg = hostaddress_arg
        self.realtime_arg = realtime_arg
        self.other_args = other_args
        self.stdout = stdout

    def __repr__(self) -> str:
        if self.name is not None:
            return f"Bot {self.name}({self.race.name} from {self.launch_list})"
        return f"Bot({self.race.name} from {self.launch_list})"

    def cmd_line(
        self, sc2port: int | str, matchport: int | str | None, hostaddress: str, realtime: bool = False
    ) -> list[str]:
        """

        :param sc2port: the port that the launched sc2 instance listens to
        :param matchport: some starting port that both bots use to generate identical portconfigs.
                Note: This will not be sent if playing vs computer
        :param hostaddress: the address the sc2 instances used
        :param realtime: 1 or 0, indicating whether the match is played in realtime or not
        :return: string that will be used to start the bot's process
        """
        cmd_line = [
            *self.launch_list,
            self.sc2port_arg,
            str(sc2port),
            self.hostaddress_arg,
            hostaddress,
        ]
        if matchport is not None:
            cmd_line.extend([self.match_arg, str(matchport)])
        if self.other_args is not None:
            cmd_line.append(self.other_args)
        if realtime:
            cmd_line.extend([self.realtime_arg])
        return cmd_line


class DockerBotProcess(BotProcess):
    """A BotProcess that runs the opponent bot inside a Docker container.

    Both SC2 instances run on the host; the container only handles bot logic.
    The container connects to the host's Proxy WebSocket via host.docker.internal.
    Works out of the box on Docker Desktop (Windows/macOS). On Linux Docker Engine,
    the Proxy may need to bind to 0.0.0.0 instead of 127.0.0.1.

    :param bot_dir: Host path to the bot directory (mounted at /root/bot_dir)
    :param race: Bot's race
    :param name: Bot's name
    :param image: Docker image with Python and bot runtime dependencies
    :param bot_command: Command to run the bot (default: ["python", "/root/bot_dir/run.py"])
    :param setup_command: Optional bash commands to run before the bot (e.g. pip install)
    :param extra_volumes: Additional volume mounts (Docker -v syntax)
    :param extra_docker_args: Additional docker run arguments
    :param stdout: File path to redirect container stdout to
    """

    def __init__(
        self,
        bot_dir: str | Path,
        race: Race,
        name: str | None = None,
        image: str = "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
        bot_command: list[str] | None = None,
        setup_command: str | None = None,
        extra_volumes: list[str] | None = None,
        extra_docker_args: list[str] | None = None,
        stdout: str | None = None,
    ) -> None:
        bot_dir = Path(bot_dir).resolve()
        super().__init__(
            path=bot_dir,
            launch_list=[],
            race=race,
            name=name,
            stdout=stdout,
        )
        self.bot_dir = bot_dir
        self.image = image
        self.bot_command = bot_command or ["python", "/root/bot_dir/run.py"]
        self.setup_command = setup_command
        self.extra_volumes = extra_volumes or []
        self.extra_docker_args = extra_docker_args or []

    def cmd_line(
        self, sc2port: int | str, matchport: int | str | None, hostaddress: str, realtime: bool = False
    ) -> list[str]:
        container_host = "host.docker.internal"

        # Build the bot run command with game args
        bot_parts = list(self.bot_command)
        bot_parts.extend([self.sc2port_arg, str(sc2port)])
        bot_parts.extend([self.hostaddress_arg, container_host])
        if matchport is not None:
            bot_parts.extend([self.match_arg, str(matchport)])
        if realtime:
            bot_parts.append(self.realtime_arg)

        # Combine setup + bot command into a single bash -c script
        bot_cmd_str = " ".join(bot_parts)
        if self.setup_command:
            script = f"{self.setup_command} && {bot_cmd_str}"
        else:
            script = bot_cmd_str

        cmd = [
            "docker", "run", "--rm",
            "--add-host=host.docker.internal:host-gateway",
            "-w", "/root/bot_dir",
            "-v", f"{self.bot_dir}:/root/bot_dir",
            "--entrypoint", "bash",
        ]
        for vol in self.extra_volumes:
            cmd.extend(["-v", vol])
        cmd.extend(self.extra_docker_args)
        cmd.append(self.image)
        cmd.extend(["-c", script])
        return cmd

    def __repr__(self) -> str:
        if self.name is not None:
            return f"DockerBot {self.name}({self.race.name} in {self.image})"
        return f"DockerBot({self.race.name} in {self.image})"

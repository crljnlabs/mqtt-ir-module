import os
from database.database_base import DatabaseBase
from database.schemas import (
    Remotes, Buttons, Signals, Captures, Settings, Agents, Marketplace,
    Scripts, ScriptSteps, ScriptRuns, ScriptRunSteps, Logs,
)


class Database(DatabaseBase):
    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir)
        os.makedirs(self._data_dir, exist_ok=True)
        self.remotes = Remotes(data_dir)
        self.buttons = Buttons(data_dir)
        self.signals = Signals(data_dir)
        self.captures = Captures(data_dir)
        self.settings = Settings(data_dir)
        self.agents = Agents(data_dir)
        self.marketplace = Marketplace(data_dir)
        self.scripts = Scripts(data_dir)
        self.script_steps = ScriptSteps(data_dir)
        self.script_runs = ScriptRuns(data_dir)
        self.script_run_steps = ScriptRunSteps(data_dir)
        self.logs = Logs(data_dir)

    def init(self) -> None:
        conn = self._connect()
        try:
            self.remotes._create_schema(conn)
            self.buttons._create_schema(conn)
            self.signals._create_schema(conn)
            self.captures._create_schema(conn)
            self.settings._create_schema(conn)
            self.agents._create_schema(conn)
            self.marketplace._create_schema(conn)
            # scripts tables must come after remotes/buttons (FK deps) and settings
            self.scripts._create_schema(conn)
            self.script_steps._create_schema(conn)
            self.script_runs._create_schema(conn)
            self.script_run_steps._create_schema(conn)
            self.logs._create_schema(conn)
            conn.commit()
        finally:
            conn.close()
            

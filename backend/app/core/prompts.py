import yaml
from pathlib import Path
from typing import Any, Dict


class PromptManager:
    _instance = None
    prompts: Dict[str, Any]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptManager, cls).__new__(cls)
            cls._instance._load_prompts()
        return cls._instance

    def _load_prompts(self):
        prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        self.prompts = {}

        if not prompts_dir.exists():
            return

        yaml_files = sorted(
            list(prompts_dir.glob("*.yaml")) + list(prompts_dir.glob("*.yml"))
        )
        for yaml_file in yaml_files:
            file_key = yaml_file.stem
            with open(yaml_file, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f) or {}
                self.prompts[file_key] = content

    def get_prompt(self, key: str, **kwargs: Any) -> str:
        keys = key.split(".")
        current = self.prompts
        for k in keys:
            if not isinstance(current, dict) or k not in current:
                raise KeyError(f"Prompt key '{key}' not found.")
            current = current[k]

        if not isinstance(current, str):
            raise ValueError(f"Prompt key '{key}' does not point to a string.")

        return current.format(**kwargs)


# Global instance for easy import
prompt_manager = PromptManager()

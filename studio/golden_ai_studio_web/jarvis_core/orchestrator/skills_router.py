from .models import ModelProfile, Route, SkillDefinition


class SkillsRouter:
    def __init__(self, registry):
        self.registry = registry
        self._skills = self._build_skills()

    def _build_skills(self):
        specs = {
            "windows": (Route.WINDOWS, ("open_program", "close_program", "open_folder", "open_file",
                "open_path", "minimize_all", "show_desktop", "close_active_window",
                "maximize_window", "minimize_window", "switch_window"), "MEDIUM", ModelProfile.FAST),
            "system": (Route.SYSTEM, ("system_status", "get_time", "get_date", "get_ip",
                "get_username", "get_battery", "get_network", "list_processes"), "LOW", ModelProfile.FAST),
            "computer_use": (Route.COMPUTER_USE, (
                "mouse_position", "mouse_move", "mouse_click", "screenshot",
                "keyboard_type", "keyboard_press", "keyboard_hotkey",
                "clipboard_get", "clipboard_set", "gpu_status", "gpu_list",
                "vision_analyze_screen", "vision_describe_screen",
                "vision_find_element", "vision_list_elements",
                "ui_active_window", "ui_find_element", "ui_list_elements",
                "ui_get_element_text", "ui_focus_window", "ui_focus_element",
                "ui_dismiss_path_not_found", "hybrid_find_ui_target",
            ), "LOW", ModelProfile.GENERAL),
            "market_data": (Route.MARKET_DATA, ("get_exchange_rate",), "LOW", ModelProfile.FAST),
            "market_analysis": (Route.MARKET_ANALYSIS, (
                "mt5_status", "mt5_account_info", "mt5_positions", "mt5_orders",
                "mt5_symbol_tick", "mt5_symbol_info", "mt5_recent_candles",
                "golden_status", "golden_scanner_status", "golden_scanner_results",
                "golden_risk_status", "web_research",
            ), "LOW", ModelProfile.GENERAL),
            "memory": (Route.MEMORY, ("memory_search", "memory_recent", "memory_remember"), "MEDIUM", ModelProfile.GENERAL),
            "vision": (Route.VISION, ("analyze_screen", "take_screenshot", "take_screenshot_window"), "MEDIUM", ModelProfile.VISION),
            "browser": (Route.BROWSER, (
                "open_url", "browser_open", "browser_navigate", "browser_get_page_info",
                "browser_read_page", "browser_get_elements", "browser_click", "browser_type",
                "browser_search", "browser_wait_for_navigation",
                "browser_scroll", "browser_back", "browser_forward", "browser_screenshot",
                "browser_close", "browser_health",
            ), "MEDIUM", ModelProfile.GENERAL),
            "web": (Route.WEB, ("web_research", "web_research_learn"), "LOW",
                    ModelProfile.GENERAL),
            "coding": (Route.CODING, (), "LOW", ModelProfile.CODING),
            "image": (Route.IMAGE, (), "LOW", ModelProfile.GENERAL),
            "video": (Route.VIDEO, (), "MEDIUM", ModelProfile.DEEP),
            "whatsapp": (Route.WHATSAPP, (), "HIGH", ModelProfile.GENERAL),
            "golden": (Route.GOLDEN, (
                "golden_status", "golden_scanner_status", "golden_scanner_results",
                "golden_risk_status",
            ), "LOW", ModelProfile.GENERAL),
            "radar": (Route.RADAR, (), "LOW", ModelProfile.GENERAL),
            "mt5": (Route.MT5, (
                "mt5_status", "mt5_account_info", "mt5_positions", "mt5_orders",
                "mt5_symbol_tick", "mt5_symbol_info", "mt5_recent_candles",
            ), "LOW", ModelProfile.GENERAL),
            "trading": (Route.TRADING, (), "HIGH", ModelProfile.DEEP),
            "task": (Route.TASK, ("open_program", "open_url", "system_status",
                "get_time", "memory_search"), "MEDIUM", ModelProfile.DEEP),
            "conversation": (Route.CONVERSATION, (), "LOW", ModelProfile.GENERAL),
        }
        skills = {}
        for name, (route, tools, risk, profile) in specs.items():
            present = tuple(tool for tool in tools if self.registry.get(tool))
            skills[name] = SkillDefinition(name, route, bool(present) or not tools, present, risk, profile)
        return skills

    def get(self, name):
        return self._skills.get(name)

    def for_route(self, route):
        return next((skill for skill in self._skills.values() if skill.route == route), None)

    def tool_names(self, skill_name):
        skill = self.get(skill_name)
        return skill.required_tools if skill else ()

    def llm_tools(self, skill_name):
        return self.registry.get_llm_tools(names=self.tool_names(skill_name))

    def catalog(self):
        return tuple(self._skills.values())

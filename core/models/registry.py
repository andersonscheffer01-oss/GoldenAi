"""Model registry for Multi-Model Local V1.

The ModelRegistry stores metadata about available models and their
profile assignments. It does NOT download models; it only tracks
what is already installed locally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .profiles import ModelProfile, get_profile_config
from .provider import ModelInfo, ModelProvider


@dataclass
class RegisteredModel:
    """A model registered in the ModelRegistry."""
    name: str
    profile: ModelProfile
    size_bytes: int = 0
    available: bool = True
    details: dict[str, Any] = field(default_factory=dict)


class ModelRegistry:
    """Tracks available models and their profile assignments."""

    def __init__(self, provider: ModelProvider | None = None, settings=None) -> None:
        self._provider = provider
        self._models: dict[str, RegisteredModel] = {}
        self._profile_to_model: dict[ModelProfile, str] = {}
        self._settings = settings
        self._init_defaults()

    def _init_defaults(self) -> None:
        """Register default models from the profile mapping."""
        # Try to use profiles from settings if provided; otherwise use defaults
        if self._settings and hasattr(self._settings, 'model_profiles'):
            # Use model_profiles from settings as primary source
            for profile_name, model_name in self._settings.model_profiles.items():
                try:
                    profile = ModelProfile(profile_name.upper())
                    self._profile_to_model[profile] = model_name
                    # Registrar o modelo apenas uma vez, mas associar ao perfil
                    if model_name not in self._models:
                        self.register(model_name, profile)
                except ValueError:
                    # If the profile name is invalid, skip it but don't crash
                    continue
        else:
            # Fallback to default profiles when no settings provided or no model_profiles defined
            for profile in ModelProfile:
                cfg = get_profile_config(profile)
                self._profile_to_model[profile] = cfg.model_name
                if cfg.model_name not in self._models:
                    self.register(cfg.model_name, profile)

    def register(
        self,
        name: str,
        profile: ModelProfile | str,
        size_bytes: int = 0,
        available: bool = True,
        details: dict[str, Any] | None = None,
    ) -> RegisteredModel:
        """Register or update a model in the registry."""
        if isinstance(profile, str):
            try:
                profile = ModelProfile(profile.upper())
            except ValueError:
                profile = ModelProfile.CODER
        model = RegisteredModel(
            name=name,
            profile=profile,
            size_bytes=size_bytes,
            available=available,
            details=details or {},
        )
        self._models[name] = model
        return model

    def get(self, name: str) -> RegisteredModel | None:
        """Return a registered model by name, or None."""
        return self._models.get(name)

    def get_by_profile(self, profile: ModelProfile | str) -> RegisteredModel | None:
        """Return the first model registered for a given profile."""
        if isinstance(profile, str):
            try:
                profile = ModelProfile(profile.upper())
            except ValueError:
                profile = ModelProfile.CODER
        
        # Primeiro tenta obter o modelo associado a este perfil
        if profile in self._profile_to_model:
            model_name = self._profile_to_model[profile]
            return self.get(model_name)
        
        # Fallback: busca no sistema original
        for model in self._models.values():
            if model.profile == profile and model.available:
                return model
        for model in self._models.values():
            if model.profile == profile:
                return model
        return None

    def list_all(self) -> list[RegisteredModel]:
        """Return all registered models."""
        return list(self._models.values())

    def list_available(self) -> list[RegisteredModel]:
        """Return only models marked as available."""
        return [m for m in self._models.values() if m.available]

    def refresh_from_provider(self) -> None:
        """Update availability by querying the provider (if set)."""
        if not self._provider:
            return
        provider_models = self._provider.list_models()
        provider_names = {m.name for m in provider_models}
        for model in self._models.values():
            model.available = model.name in provider_names
            for pm in provider_models:
                if pm.name == model.name:
                    model.size_bytes = pm.size_bytes
                    model.details = pm.details
                    break

    def get_model_name_for_profile(self, profile: ModelProfile | str) -> str:
        """Return the model name for a profile, falling back to CODER."""
        # Primeiro tenta obter através da associação perfil->modelo
        if isinstance(profile, str):
            try:
                profile = ModelProfile(profile.upper())
            except ValueError:
                profile = ModelProfile.CODER
        
        if profile in self._profile_to_model:
            return self._profile_to_model[profile]
            
        # Fallback para o padrão
        model = self.get_by_profile(profile)
        if model:
            return model.name
        # Se ainda não encontrou, usa a configuração padrão do perfil
        try:
            cfg = get_profile_config(profile)
            return cfg.model_name
        except ValueError:
            cfg = get_profile_config(ModelProfile.CODER)
            return cfg.model_name

from __future__ import annotations

from knowledge.data_loader import load_knowledge_pack
from knowledge.knowledge_schema import KnowledgePack, Resource, SourceNode


class ResourceDB:
    def __init__(self, pack: KnowledgePack | None = None) -> None:
        self._pack = pack or load_knowledge_pack()
        self._resources = {item.resource_id: item for item in self._pack.resources}
        self._sources = {item.source_id: item for item in self._pack.sources}

    @property
    def pack(self) -> KnowledgePack:
        return self._pack

    def resolve_resource(self, resource_id_or_name: str) -> Resource | None:
        needle = resource_id_or_name.lower()
        for resource in self._resources.values():
            if resource.resource_id.lower() == needle or resource.name.lower() == needle:
                return resource
        return None

    def list_sources(self, resource: Resource) -> list[SourceNode]:
        return [self._sources[item.source_id] for item in resource.sources if item.source_id in self._sources]


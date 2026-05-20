from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app_service.agent_controller import AgentController
from app_service.schemas import (
    AgentStateSummary,
    CommandResult,
    ConfigResponse,
    CalibrationProfileModel,
    CalibrationProfileSaveRequest,
    CalibrationProfilesResponse,
    CalibrationTestRequest,
    CalibrationTestResponse,
    CombatPlaybookRequest,
    CombatPlaybookResponse,
    DiagnosticsResponse,
    HealthResponse,
    DangerEventRequest,
    DangerEventResponse,
    FailureExplanationRequest,
    FailureExplanationResponse,
    LatestRunResponse,
    KnowledgeResolveResponse,
    MissionPlanRequest,
    MissionPlanResponse,
    ModelBenchmarkResponse,
    ModelCommandResponse,
    ModelLoadRequest,
    ModelStatusResponse,
    PersonaEventRequest,
    PersonaEventResponse,
    PersonaProfileModel,
    PlannerRequest,
    PlannerResponse,
    ProductChecklistResponse,
    ProductLatestReportResponse,
    ProductRunE2ERequest,
    ProductRunE2EResponse,
    RouteRankResponse,
    ShowcaseLatestReportResponse,
    ShowcaseRunRequest,
    ShowcaseRunResponse,
    SkillDefinitionModel,
    SkillDryRunResponse,
    SkillListResponse,
    SkillRecordCommandResponse,
    SkillRecordEventRequest,
    SkillRecordMarkerRequest,
    SkillRecordSaveRequest,
    SkillRecordStartRequest,
    SkillReplayRequest,
    SkillReplayResponse,
    SkillValidationResponse,
    SkillVersionsResponse,
    WindowListResponse,
    WindowSelectRequest,
    WindowSelectResponse,
)
from app_service.skill_manager import SkillValidationError
from app_service.window_selector import WindowSelectionError


def create_api_router(controller: AgentController) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="OK")

    @router.get("/state", response_model=AgentStateSummary)
    def state() -> AgentStateSummary:
        return AgentStateSummary(**asdict(controller.state()))

    @router.post("/agent/start", response_model=CommandResult)
    def start() -> CommandResult:
        return CommandResult(ok=True, state=AgentStateSummary(**asdict(controller.start())))

    @router.post("/agent/pause", response_model=CommandResult)
    def pause() -> CommandResult:
        return CommandResult(ok=True, state=AgentStateSummary(**asdict(controller.pause())))

    @router.post("/agent/resume", response_model=CommandResult)
    def resume() -> CommandResult:
        return CommandResult(ok=True, state=AgentStateSummary(**asdict(controller.resume())))

    @router.post("/agent/stop", response_model=CommandResult)
    def stop() -> CommandResult:
        return CommandResult(ok=True, state=AgentStateSummary(**asdict(controller.stop())))

    @router.post("/agent/emergency_stop", response_model=CommandResult)
    def emergency_stop() -> CommandResult:
        return CommandResult(
            ok=True,
            state=AgentStateSummary(**asdict(controller.emergency_stop())),
        )

    @router.get("/runs/latest", response_model=LatestRunResponse)
    def latest_run() -> LatestRunResponse:
        return LatestRunResponse(**controller.latest_run())

    @router.get("/config/current", response_model=ConfigResponse)
    def current_config() -> ConfigResponse:
        return ConfigResponse(**controller.current_config())

    @router.post("/diagnostics/run", response_model=DiagnosticsResponse)
    def diagnostics_run() -> DiagnosticsResponse:
        return DiagnosticsResponse(**controller.run_diagnostics())

    @router.get("/windows", response_model=WindowListResponse)
    def windows() -> WindowListResponse:
        return WindowListResponse(**controller.list_windows())

    @router.post("/window/select", response_model=WindowSelectResponse)
    def select_window(request: WindowSelectRequest) -> WindowSelectResponse:
        try:
            window = controller.select_window(title=request.title, handle=request.handle)
        except WindowSelectionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return WindowSelectResponse(ok=True, window=window.to_dict())

    @router.get("/capture/snapshot")
    def capture_snapshot() -> Response:
        try:
            return Response(content=controller.snapshot_png(), media_type="image/png")
        except WindowSelectionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/calibration/profile", response_model=CalibrationProfileModel)
    def save_calibration_profile(request: CalibrationProfileSaveRequest) -> CalibrationProfileModel:
        profile = controller.save_calibration_profile(request.profile.model_dump(), activate=request.activate)
        return CalibrationProfileModel(**asdict(profile))

    @router.get("/calibration/profiles", response_model=CalibrationProfilesResponse)
    def calibration_profiles() -> CalibrationProfilesResponse:
        return CalibrationProfilesResponse(**controller.list_calibration_profiles())

    @router.get("/calibration/profiles/{profile_id}", response_model=CalibrationProfileModel)
    def calibration_profile(profile_id: str) -> CalibrationProfileModel:
        try:
            return CalibrationProfileModel(**asdict(controller.get_calibration_profile(profile_id)))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/calibration/profiles/{profile_id}/restore", response_model=CalibrationProfileModel)
    def restore_calibration_profile(profile_id: str) -> CalibrationProfileModel:
        try:
            return CalibrationProfileModel(**asdict(controller.restore_calibration_profile(profile_id)))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/calibration/test", response_model=CalibrationTestResponse)
    def calibration_test(request: CalibrationTestRequest | None = None) -> CalibrationTestResponse:
        result = controller.test_calibration_profile(request.profile_id if request else None)
        return CalibrationTestResponse(**result)

    @router.get("/models/status", response_model=ModelStatusResponse)
    def models_status() -> ModelStatusResponse:
        return ModelStatusResponse(**controller.model_status())

    @router.post("/models/load", response_model=ModelCommandResponse)
    def models_load(request: ModelLoadRequest | None = None) -> ModelCommandResponse:
        return ModelCommandResponse(**controller.load_model(request.model_path if request else None))

    @router.post("/models/benchmark", response_model=ModelBenchmarkResponse)
    def models_benchmark() -> ModelBenchmarkResponse:
        return ModelBenchmarkResponse(**controller.benchmark_model())

    @router.post("/skills/record/start", response_model=SkillRecordCommandResponse)
    def skill_record_start(request: SkillRecordStartRequest | None = None) -> SkillRecordCommandResponse:
        try:
            return SkillRecordCommandResponse(**controller.skill_record_start((request.backend if request else "mock")))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/skills/record/event", response_model=SkillRecordCommandResponse)
    def skill_record_event(request: SkillRecordEventRequest) -> SkillRecordCommandResponse:
        return SkillRecordCommandResponse(**controller.skill_record_event(request.model_dump()))

    @router.post("/skills/record/marker", response_model=SkillRecordCommandResponse)
    def skill_record_marker(request: SkillRecordMarkerRequest) -> SkillRecordCommandResponse:
        return SkillRecordCommandResponse(**controller.skill_record_marker(request.marker))

    @router.post("/skills/record/stop", response_model=SkillRecordCommandResponse)
    def skill_record_stop() -> SkillRecordCommandResponse:
        try:
            return SkillRecordCommandResponse(**controller.skill_record_stop())
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/skills/record/current", response_model=SkillRecordCommandResponse)
    def skill_record_current() -> SkillRecordCommandResponse:
        return SkillRecordCommandResponse(**controller.skill_record_current())

    @router.post("/skills/record/save", response_model=SkillDefinitionModel)
    def skill_record_save(request: SkillRecordSaveRequest) -> SkillDefinitionModel:
        try:
            return SkillDefinitionModel(**controller.skill_record_save(request.skill_id, request.name))
        except (RuntimeError, SkillValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/skills", response_model=SkillListResponse)
    def skills() -> SkillListResponse:
        return SkillListResponse(**controller.list_skills())

    @router.get("/skills/{skill_id}", response_model=SkillDefinitionModel)
    def skill(skill_id: str) -> SkillDefinitionModel:
        try:
            return SkillDefinitionModel(**controller.get_skill(skill_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/skills", response_model=SkillDefinitionModel)
    def create_skill(request: SkillDefinitionModel) -> SkillDefinitionModel:
        try:
            return SkillDefinitionModel(**controller.save_skill(request.model_dump()))
        except SkillValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.put("/skills/{skill_id}", response_model=SkillDefinitionModel)
    def update_skill(skill_id: str, request: SkillDefinitionModel) -> SkillDefinitionModel:
        try:
            return SkillDefinitionModel(**controller.update_skill(skill_id, request.model_dump()))
        except SkillValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/skills/{skill_id}/validate", response_model=SkillValidationResponse)
    def validate_skill(skill_id: str) -> SkillValidationResponse:
        try:
            return SkillValidationResponse(**controller.validate_skill(skill_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/skills/{skill_id}/dry_run", response_model=SkillDryRunResponse)
    def dry_run_skill(skill_id: str) -> SkillDryRunResponse:
        try:
            return SkillDryRunResponse(**controller.dry_run_skill(skill_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/skills/{skill_id}/replay", response_model=SkillReplayResponse)
    def replay_skill(skill_id: str, request: SkillReplayRequest) -> SkillReplayResponse:
        try:
            return SkillReplayResponse(**controller.replay_skill(skill_id, mode=request.mode, confirm=request.confirm))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/skills/{skill_id}/archive", response_model=SkillDefinitionModel)
    def archive_skill(skill_id: str) -> SkillDefinitionModel:
        try:
            return SkillDefinitionModel(**controller.archive_skill(skill_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/skills/{skill_id}/versions", response_model=SkillVersionsResponse)
    def skill_versions(skill_id: str) -> SkillVersionsResponse:
        return SkillVersionsResponse(**controller.skill_versions(skill_id))

    @router.post("/skills/{skill_id}/rollback", response_model=SkillDefinitionModel)
    def skill_rollback(skill_id: str, version_file: str | None = None) -> SkillDefinitionModel:
        try:
            return SkillDefinitionModel(**controller.skill_rollback(skill_id, version_file))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/persona/profiles", response_model=dict[str, list[PersonaProfileModel]])
    def persona_profiles() -> dict[str, list[PersonaProfileModel]]:
        return {"personas": [PersonaProfileModel(**item) for item in controller.list_personas()["personas"]]}

    @router.post("/persona/event", response_model=PersonaEventResponse)
    def persona_event(request: PersonaEventRequest) -> PersonaEventResponse:
        return PersonaEventResponse(**controller.persona_event(request.event_code, request.payload, request.persona_id))

    @router.post("/planner/task", response_model=PlannerResponse)
    def planner_task(request: PlannerRequest) -> PlannerResponse:
        return PlannerResponse(**controller.plan_task(goal=request.goal, provider=request.provider, persona_id=request.persona_id))

    @router.get("/knowledge/resolve", response_model=KnowledgeResolveResponse)
    def knowledge_resolve(goal: str) -> KnowledgeResolveResponse:
        return KnowledgeResolveResponse(**controller.resolve_resource(goal))

    @router.get("/knowledge/routes", response_model=RouteRankResponse)
    def knowledge_routes(resource_id: str) -> RouteRankResponse:
        return RouteRankResponse(**controller.rank_routes(resource_id))

    @router.post("/mission/plan", response_model=MissionPlanResponse)
    def mission_plan(request: MissionPlanRequest) -> MissionPlanResponse:
        return MissionPlanResponse(**controller.build_mission_queue(request.goal))

    @router.post("/planner/explain_failure", response_model=FailureExplanationResponse)
    def planner_explain_failure(request: FailureExplanationRequest) -> FailureExplanationResponse:
        return FailureExplanationResponse(**controller.explain_failure(summary=request.summary, provider=request.provider))

    @router.post("/combat/playbook", response_model=CombatPlaybookResponse)
    def combat_playbook(request: CombatPlaybookRequest) -> CombatPlaybookResponse:
        return CombatPlaybookResponse(**controller.create_combat_playbook(request.goal, request.team_profile, request.provider))

    @router.post("/combat/danger", response_model=DangerEventResponse)
    def combat_danger(request: DangerEventRequest) -> DangerEventResponse:
        return DangerEventResponse(**controller.evaluate_danger(request.signals, request.context_priority))

    @router.get("/product/checklist", response_model=ProductChecklistResponse)
    def product_checklist(profile: str | None = None, skill: str | None = None, task: str = "complete product demo") -> ProductChecklistResponse:
        return ProductChecklistResponse(**controller.product_checklist(profile=profile, skill=skill, task=task))

    @router.post("/product/run_e2e", response_model=ProductRunE2EResponse)
    def product_run_e2e(request: ProductRunE2ERequest) -> ProductRunE2EResponse:
        return ProductRunE2EResponse(
            **controller.run_product_e2e(
                mode=request.mode,
                seconds=request.seconds,
                profile=request.profile,
                skill=request.skill,
                task=request.task,
                use_mock_llm=request.use_mock_llm,
                chaos=request.chaos,
                confirm=request.confirm,
            )
        )

    @router.get("/product/latest_report", response_model=ProductLatestReportResponse)
    def product_latest_report() -> ProductLatestReportResponse:
        return ProductLatestReportResponse(**controller.product_latest_report())

    @router.post("/showcase/run", response_model=ShowcaseRunResponse)
    def showcase_run(request: ShowcaseRunRequest) -> ShowcaseRunResponse:
        return ShowcaseRunResponse(
            **controller.run_showcase(
                mode=request.mode,
                seconds=request.seconds,
                persona=request.persona,
                provider=request.provider,
                target_window_title=request.target_window_title,
            )
        )

    @router.get("/showcase/latest_report", response_model=ShowcaseLatestReportResponse)
    def showcase_latest_report() -> ShowcaseLatestReportResponse:
        return ShowcaseLatestReportResponse(**controller.showcase_latest_report())

    return router

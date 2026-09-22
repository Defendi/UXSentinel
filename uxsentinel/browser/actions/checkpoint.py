from __future__ import annotations

from typing import TYPE_CHECKING

from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler

if TYPE_CHECKING:
    pass


class CheckpointActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        if not ctx.agent:
            raise RuntimeError("CheckpointActionHandler requer ctx.agent para invocar _handle_checkpoint")
        await ctx.agent._handle_checkpoint(
            ctx.step,
            ctx.driver,
            ctx.report,
            ctx.out_dir,
            progress=ctx.progress,
            task_id=ctx.task_id,
            step_index=ctx.step_index,
            total_steps=len(ctx.scenario.steps),
            current_viewport=ctx.current_viewport,
            multi_viewport=ctx.multi_viewport,
            effective_axe=ctx.effective_axe,
            effective_css=getattr(ctx, "effective_css", True),
            effective_baseline_dir=ctx.effective_baseline_dir,
            effective_update_baseline=ctx.effective_update_baseline,
            effective_diff_threshold=ctx.effective_diff_threshold,
            scenario_exceptions=ctx.scenario.exceptions,
        )

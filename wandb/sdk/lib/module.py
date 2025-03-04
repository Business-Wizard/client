import wandb

from . import preinit


def set_global(
    run=None,
    config=None,
    log=None,
    summary=None,
    save=None,
    use_artifact=None,
    log_artifact=None,
    alert=None,
    plot_table=None,
):
    if run:
        wandb.run = run
    if config is not None:
        wandb.config = config
    if log:
        wandb.log = log
    if summary is not None:
        wandb.summary = summary
    if save:
        wandb.save = save
    if use_artifact:
        wandb.use_artifact = use_artifact
    if log_artifact:
        wandb.log_artifact = log_artifact
    if plot_table:
        wandb.plot_table = plot_table
    if alert:
        wandb.alert = alert


def unset_globals():
    wandb.run = None
    wandb.config = preinit.PreInitObject("wandb.config")
    wandb.summary = preinit.PreInitObject("wandb.summary")
    wandb.log = preinit.PreInitCallable("wandb.log", wandb.wandb_sdk.wandb_run.Run.log)
    wandb.save = preinit.PreInitCallable(
        "wandb.save", wandb.wandb_sdk.wandb_run.Run.save
    )
    wandb.use_artifact = preinit.PreInitCallable(
        "wandb.use_artifact", wandb.wandb_sdk.wandb_run.Run.use_artifact
    )
    wandb.log_artifact = preinit.PreInitCallable(
        "wandb.log_artifact", wandb.wandb_sdk.wandb_run.Run.log_artifact
    )

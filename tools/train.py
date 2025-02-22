import datetime
import os
import re
from pathlib import Path

import click
import hydra
from loguru import logger
from omegaconf import OmegaConf


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="test/test2.yaml",
    help="config name",
)
@click.option("--entity", "-e", type=str, default="fish-audio", help="entity for wandb")
@click.option("--tensorboard", "-t", is_flag=True, help="Log to tensorboard")
@click.option(
    "--resume", "-r", is_flag=True, help="Resume training using the latest ckpt"
)
@click.option(
    "--resume-id", "-i", type=str, default=None, help="Resume id for training"
)
@click.option(
    "--checkpoint",
    "-p",
    type=click.Path(exists=True),
    default=None,
    help="Resume training ckpt file",
    callback=lambda ctx, param, value: value
    if value is None or value.endswith(".ckpt")
    else None,
    show_default=True,
)
@click.option("--name", "-n", type=str, default=None, help="Run name for wandb")
@click.option(
    "pretrained",
    "--pretrained",
    "-pre",
    is_flag=True,
    help="Use pretrained. Make sure to specify checkpoint using -p",
)
@click.option("--help", "-h", is_flag=True, help="Show help")
def main(
    config, entity, tensorboard, resume, resume_id, checkpoint, name, pretrained, help
):
    if help:
        click.echo(click.get_current_context().get_help())
        return
    run_dir = Path(config).parent
    config = Path(config).stem
    logger.info(f"Running {config} in {run_dir}")
    with hydra.initialize(config_path=f"../{run_dir}", job_name=run_dir):
        cfg = hydra.compose(config_name=config)
        model = cfg.model.type
        OmegaConf.set_struct(cfg, False)  # Allow changes to the config
        cfg.name = str(run_dir) if name is None else name
        cfg.entity = entity
        cfg.tensorboard = tensorboard
        cfg.run_dir = str(run_dir)
        OmegaConf.set_struct(cfg, True)

        if model == "DiffSVC":
            from tools.diffusion.train import train
        elif model == "HiFiSVC":
            from tools.hifisinger.train import train
        else:
            logger.error(f"Unknown model type {model}")
            raise ValueError(f"Unknown model type {model}")

        if resume:
            if resume_id is None:
                # get id from logs/model/resume_id/xxx.ckpt
                resume_ids = sorted(
                    [
                        path
                        for path in (run_dir / Path("logs") / model).glob("*")
                        if re.match("^[a-zA-Z0-9]+$", str(path.name))
                    ],
                    key=os.path.getctime,
                )
                if len(resume_ids) == 0:
                    raise ValueError("No resume id found")
                elif len(resume_ids) > 1:
                    # get the latest one
                    logger.warning(
                        f"Multiple resume ids found, using the latest one {resume_ids[-1]}"
                    )
                cfg.resume_id = resume_ids[-1].name
                # get the latest checkpoint from the resume id/ folder
            else:
                cfg.resume_id = resume_id

            if checkpoint is not None:
                cfg.resume = checkpoint
            else:
                ckpts = sorted(
                    (
                        cfg.run_dir
                        / Path("logs")
                        / model
                        / cfg.resume_id
                        / "checkpoints"
                    ).glob("*.ckpt"),
                    key=os.path.getctime,
                )
                if len(ckpts) == 0:
                    raise ValueError(f"No checkpoint found in {cfg.resume_id}")
                elif len(ckpts) > 1:
                    # get the latest one
                    logger.warning(
                        f"Multiple checkpoints found, using the latest one {ckpts[-1]}"
                    )
                cfg.resume = ckpts[-1]

        if pretrained:
            if checkpoint is not None:
                cfg.pretrained = checkpoint
            else:
                logger.warning("No pretrained checkpoint specified")
                raise ValueError("No pretrained checkpoint specified")
        # save config for this run
        curr_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cfg_path = Path(f"{run_dir}/logs") / model / curr_time / "config.yaml"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        OmegaConf.save(cfg, f"{cfg_path}")
        train(cfg)


if __name__ == "__main__":
    main()

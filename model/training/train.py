"""
YOLOv8 training script for PPE detection.
"""
import os
import sys
import yaml
import argparse
import torch
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "model", "ppe_config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


def train_yolo(
    data_yaml_path: str,
    pretrained: bool = True,
    weights_path: str = None,
    resume: bool = False,
):
    """
    Train YOLOv8 model on PPE dataset.

    Args:
        data_yaml_path: Path to data.yaml file
        pretrained: Whether to start from pretrained weights (e.g. yolov8n.pt)
        weights_path: Optional explicit initial weights file (.pt)
        resume: If True, continue training from a previous checkpoint (best.pt/last.pt)
    """

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Installing ultralytics package...")
        os.system("pip install ultralytics")
        from ultralytics import YOLO
    
    model_name = config['model']['name']
    weights_dir = config['paths']['weights']
    
    os.makedirs(weights_dir, exist_ok=True)
    os.makedirs(config['paths']['logs'], exist_ok=True)
    
    # Initialize model
    if resume:
        # Resume/continue training from previously trained checkpoint.
        # Ultralytics accepts a checkpoint/weights file path; we auto-detect best/last.
        resume_candidates = [
            # if caller passes weights_path, treat it as explicit resume weights
            weights_path,
            # repo-trained checkpoints (current training script)
            os.path.join(weights_dir, 'ppe_detection', 'weights', 'last.pt'),
            os.path.join(weights_dir, 'ppe_detection', 'weights', 'best.pt'),
            # fallbacks for older/custom layouts
            os.path.join(weights_dir, 'last.pt'),
            os.path.join(weights_dir, 'best.pt'),
        ]
        resume_candidates = [p for p in resume_candidates if p]


        resolved_resume = None
        for p in resume_candidates:
            try:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    resolved_resume = p
                    break
            except OSError:
                continue

        if not resolved_resume:
            raise FileNotFoundError(
                "--resume requested but no checkpoint found. Looked for: "
                + ", ".join(str(p) for p in resume_candidates)
            )

        print(f"Resuming training from: {resolved_resume}")
        model = YOLO(resolved_resume)

    elif weights_path is not None:
        print(f"Loading custom weights: {weights_path}")
        model = YOLO(weights_path)

    elif pretrained:
        print(f"Loading pretrained {model_name}...")
        model = YOLO(f"{model_name}.pt")

    else:
        print(f"Creating {model_name} from scratch...")
        model = YOLO(f"{model_name}.yaml")


    
    # Training arguments
    train_config = config['training']
    args = {
        'data': data_yaml_path,
        'epochs': train_config['epochs'],
        'batch': train_config['batch_size'],
        'lr0': train_config['lr'],
        'optimizer': train_config['optimizer'],
        'patience': train_config['patience'],
        'seed': train_config['seed'],
        'imgsz': config['model']['input_size'],
        'project': str(weights_dir),
        'name': 'ppe_detection',
        'exist_ok': True,
        'pretrained': pretrained,
        'device': config['model']['device'],
        'cos_lr': True,
        'close_mosaic': 10,
        'workers': 2,
        'amp': False,
    }
    
    if train_config.get('augment'):
        args.update({
            'hsv_h': 0.015,
            'hsv_s': 0.7,
            'hsv_v': 0.4,
            'degrees': 10.0,
            'translate': 0.1,
            'scale': 0.5,
            'shear': 2.0,
            'perspective': 0.0,
            'flipud': 0.1,
            'fliplr': 0.5,
            'mosaic': train_config.get('mosaic', 1.0),
            'mixup': train_config.get('mixup', 0.1),
            'copy_paste': 0.1,
        })
    
    print(f"\n{'=' * 60}")
    print(f"Starting YOLOv8 Training for PPE Detection")
    print(f"{'=' * 60}")
    print(f"Model: {model_name}")
    print(f"Dataset: {data_yaml_path}")
    print(f"Epochs: {args['epochs']}")
    print(f"Batch Size: {args['batch']}")
    print(f"Learning Rate: {args['lr0']}")
    print(f"Image Size: {args['imgsz']}")
    print(f"Device: {args['device']}")
    print(f"{'=' * 60}\n")
    
    # Train
    # If resume=True, Ultralytics will load the checkpoint and continue training.
    # We pass resume through explicitly to avoid re-starting from pretrained.
    if resume:
        args["resume"] = True

    results = model.train(**args)

    
    print(f"\n{'=' * 60}")
    print(f"Training Complete!")
    print(f"Best weights saved to: {os.path.join(weights_dir, 'ppe_detection', 'weights', 'best.pt')}")
    print(f"{'=' * 60}")
    
    return results


def export_model(weights_path: str, format: str = 'onnx'):
    """
    Export trained model to deployment format.
    
    Args:
        weights_path: Path to trained .pt weights
        format: Export format (onnx, torchscript, openvino, etc.)
    """
    from ultralytics import YOLO
    
    print(f"\nExporting model to {format} format...")
    model = YOLO(weights_path)
    
    export_path = model.export(format=format)
    print(f"Model exported to: {export_path}")
    
    return export_path


def validate_model(weights_path: str, data_yaml_path: str):
    """
    Validate trained model on test set.
    """
    from ultralytics import YOLO
    
    print(f"\nValidating model: {weights_path}")
    model = YOLO(weights_path)
    
    results = model.val(
        data=data_yaml_path,
        imgsz=config['model']['input_size'],
        conf=config['model']['conf_threshold'],
        iou=config['model']['iou_threshold'],
        device=config['model']['device'],
    )
    
    print(f"\nValidation Results:")
    print(f"  mAP@0.5: {results.box.map50:.4f}")
    print(f"  mAP@0.5:0.95: {results.box.map:.4f}")
    print(f"  Precision: {results.box.mp:.4f}")
    print(f"  Recall: {results.box.mr:.4f}")
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLOv8 PPE Training")
    parser.add_argument("--data", type=str, default="./dataset_ppe_yolo/data.yaml",
                        help="Path to data.yaml")
    parser.add_argument("--weights", type=str, default=None,
                        help="Path to (initial) weights to load before training")
    parser.add_argument("--validate", action="store_true",
                        help="Only run validation")
    parser.add_argument("--export", type=str, default=None,
                        help="Export to format (onnx, torchscript)")
    parser.add_argument("--no-pretrained", action="store_true",
                        help="Train from scratch")

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume/continue training from the previously trained local checkpoint "
            "(best.pt/last.pt under config['paths']['weights'])."
        ),
    )
    parser.add_argument(
        "--resume-weights",
        type=str,
        default=None,
        help="Optional explicit checkpoint path to resume from (overrides auto-detection).",
    )
    args = parser.parse_args()

    
    # First run dataset preparation
    print("Running dataset preparation...")
    from model.training.prepare_dataset import convert_dataset, verify_dataset
    
    output_dir = convert_dataset()
    verify_dataset(output_dir)
    
    data_yaml = args.data if os.path.exists(args.data) else os.path.join(output_dir, "data.yaml")
    
    if args.validate and args.weights:
        validate_model(args.weights, data_yaml)
    elif args.export and args.weights:
        export_model(args.weights, args.export)
    else:
        # If --resume is set, we continue training from the previously trained checkpoint
        # (best.pt/last.pt under config['paths']['weights']).
        train_yolo(
            data_yaml,
            pretrained=not args.no_pretrained,
            weights_path=(args.resume_weights if args.resume_weights is not None else args.weights),
            resume=args.resume,
        )

        # Validate after training

        weights_path = os.path.join(
            config['paths']['weights'],
            'ppe_detection',
            'weights',
            'best.pt'
        )
        if os.path.exists(weights_path):
            validate_model(weights_path, data_yaml)
            export_model(weights_path, 'onnx')
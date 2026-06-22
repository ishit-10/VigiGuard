"""
Dataset preparation script for YOLOv8 PPE detection.
Converts VOC XML + metadata into YOLO format and organizes train/val splits.
"""
import os
import sys
import json
import yaml
import shutil
import random
from pathlib import Path
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                           "config", "model", "ppe_config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

CLASSES = config['classes']  # {'person': 0, 'tools': 7, 'helmet': 10, 'hands': 11, 'shoes': 14, 'safety_suit': 15}

# Force re-index classes to 0-based contiguous for YOLO
YOLO_CLASSES = {
    'person': 0,
    'helmet': 1,
    'hands': 2,
    'shoes': 3,
    'safety_suit': 4,
    'tools': 5
}

CLASS_NAMES = {v: k for k, v in YOLO_CLASSES.items()}

DATASET_DIR = config['paths']['dataset']
OUTPUT_DIR = os.path.join(os.path.dirname(DATASET_DIR), "dataset_ppe_yolo")

def parse_voc_xml(xml_path: str) -> List[Dict]:
    """Parse a VOC XML file and extract objects."""
    try:
        tree = ET.parse(xml_path)
    except Exception as e:
        raise Exception(f"Invalid XML file {xml_path}: {e}")
    root = tree.getroot()
    
    size = root.find('size')
    width = int(size.find('width').text)
    height = int(size.find('height').text)
    
    objects = []
    for obj in root.findall('object'):
        name = obj.find('name').text
        if name not in YOLO_CLASSES:
            continue
            
        bndbox = obj.find('bndbox')
        xmin = float(bndbox.find('xmin').text)
        ymin = float(bndbox.find('ymin').text)
        xmax = float(bndbox.find('xmax').text)
        ymax = float(bndbox.find('ymax').text)
        
        # Convert to YOLO format: class_id x_center y_center width height (normalized)
        x_center = ((xmin + xmax) / 2) / width
        y_center = ((ymin + ymax) / 2) / height
        box_width = (xmax - xmin) / width
        box_height = (ymax - ymin) / height
        
        # Clamp values to [0, 1]
        x_center = max(0.0, min(1.0, x_center))
        y_center = max(0.0, min(1.0, y_center))
        box_width = max(0.0, min(1.0, box_width))
        box_height = max(0.0, min(1.0, box_height))
        
        objects.append({
            'class_id': YOLO_CLASSES[name],
            'x_center': x_center,
            'y_center': y_center,
            'width': box_width,
            'height': box_height
        })
    
    return objects

def convert_dataset():
    """Convert VOC dataset to YOLO format."""
    print("=" * 60)
    print("Converting PPE Dataset to YOLO Format")
    print("=" * 60)
    
    # New dataset layout uses YOLO labels already (dataset/train, dataset/val).
    # Old layout used VOC XML + metadata (dataset/voc_labels, dataset/images + train_files.txt/val_files.txt).
    voc_dir = os.path.join(DATASET_DIR, "voc_labels")
    images_dir = os.path.join(DATASET_DIR, "images")

    train_out = os.path.join(OUTPUT_DIR, "images", "train")
    val_out = os.path.join(OUTPUT_DIR, "images", "val")
    train_label_out = os.path.join(OUTPUT_DIR, "labels", "train")
    val_label_out = os.path.join(OUTPUT_DIR, "labels", "val")

    # If YOLO-ready dataset split folders exist, we skip VOC->YOLO conversion.
    if os.path.exists(os.path.join(DATASET_DIR, 'train', 'images')) and os.path.exists(os.path.join(DATASET_DIR, 'train', 'labels')):
        train_yolo_images = os.path.join(DATASET_DIR, 'train', 'images')
        val_yolo_images = os.path.join(DATASET_DIR, 'val', 'images')
        train_yolo_labels = os.path.join(DATASET_DIR, 'train', 'labels')
        val_yolo_labels = os.path.join(DATASET_DIR, 'val', 'labels')

        # Destination YOLO structure expected by Ultralytics
        os.makedirs(train_out, exist_ok=True)
        os.makedirs(val_out, exist_ok=True)
        os.makedirs(train_label_out, exist_ok=True)
        os.makedirs(val_label_out, exist_ok=True)


        # Copy/symlink images and labels
        for split_src_img, split_src_lbl, split_dst_img, split_dst_lbl in [
            (train_yolo_images, train_yolo_labels, train_out, train_label_out),
            (val_yolo_images, val_yolo_labels, val_out, val_label_out),
        ]:
            for img_name in os.listdir(split_src_img):
                if not any(img_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
                    continue
                src_img = os.path.join(split_src_img, img_name)
                dst_img = os.path.join(split_dst_img, img_name)
                if not os.path.exists(dst_img):
                    os.symlink(os.path.abspath(src_img), dst_img)

                base = os.path.splitext(img_name)[0]
                # labels are in YOLO .txt format with same base name
                src_lbl = os.path.join(split_src_lbl, base + '.txt')
                dst_lbl = os.path.join(split_dst_lbl, base + '.txt')
                if os.path.exists(src_lbl) and not os.path.exists(dst_lbl):
                    os.symlink(os.path.abspath(src_lbl), dst_lbl)

        # Create data.yaml expected by ultralytics
        data_yaml = {
            'path': os.path.abspath(OUTPUT_DIR),
            'train': os.path.join(os.path.abspath(OUTPUT_DIR), 'images', 'train'),
            'val': os.path.join(os.path.abspath(OUTPUT_DIR), 'images', 'val'),
            'nc': len(YOLO_CLASSES),
            'names': [CLASS_NAMES[i] for i in range(len(YOLO_CLASSES))]
        }
        data_yaml_path = os.path.join(OUTPUT_DIR, 'data.yaml')
        with open(data_yaml_path, 'w') as f:
            yaml.dump(data_yaml, f, default_flow_style=False)

        print(f"\nYOLO-ready dataset detected. data.yaml created at: {data_yaml_path}")
        print(f"YOLO dataset ready at: {OUTPUT_DIR}")
        return OUTPUT_DIR

    
    train_out = os.path.join(OUTPUT_DIR, "images", "train")
    val_out = os.path.join(OUTPUT_DIR, "images", "val")
    train_label_out = os.path.join(OUTPUT_DIR, "labels", "train")
    val_label_out = os.path.join(OUTPUT_DIR, "labels", "val")
    
    os.makedirs(train_out, exist_ok=True)
    os.makedirs(val_out, exist_ok=True)
    os.makedirs(train_label_out, exist_ok=True)
    os.makedirs(val_label_out, exist_ok=True)
    
    # Read train/val splits (only for old VOC layout)
    train_files = set()
    val_files = set()
    
    train_list_path = os.path.join(DATASET_DIR, "train_files.txt")
    val_list_path = os.path.join(DATASET_DIR, "val_files.txt")

    
    if os.path.exists(train_list_path):
        with open(train_list_path, 'r') as f:
            for line in f:
                train_files.add(line.strip())
    
    if os.path.exists(val_list_path):
        with open(val_list_path, 'r') as f:
            for line in f:
                val_files.add(line.strip())
    
    print(f"Train files: {len(train_files)}")
    print(f"Val files: {len(val_files)}")
    
    # Process all XML files
    total_images = 0
    converted_train = 0
    converted_val = 0
    class_counts = {v: 0 for v in YOLO_CLASSES.values()}
    
    for xml_file in sorted(os.listdir(voc_dir)):
        if not xml_file.endswith('.xml'):
            continue

        print(f"Processing: {xml_file}")
        
        base_name = xml_file.replace('.xml', '')
        
        # Find corresponding image
        image_found = None
        for ext in ['.jpg', '.jpeg', '.png']:
            img_path = os.path.join(images_dir, f"{base_name}{ext}")
            if os.path.exists(img_path):
                image_found = img_path
                break
        
        if image_found is None:
            print(f"  WARNING: No image found for {xml_file}")
            continue
        
        # Parse VOC XML
        xml_path = os.path.join(voc_dir, xml_file)
        try:
            objects = parse_voc_xml(xml_path)
        except Exception as e:
            print(f"  ERROR parsing {xml_file}: {e}")
            continue
        
        if len(objects) == 0:
            print(f"  WARNING: No valid objects in {xml_file}, skipping")
            continue
        
        # Get image file name from listing
        image_filename = os.path.basename(image_found)
        
        # Determine if train or val
        is_val = image_filename in val_files
        is_train = image_filename in train_files
        
        if is_val:
            dest_img_dir = val_out
            dest_label_dir = val_label_out
            converted_val += 1
        elif is_train:
            dest_img_dir = train_out
            dest_label_dir = train_label_out
            converted_train += 1
        else:
            # Default: 80/20 split for unseen files
            if random.random() < 0.2:
                dest_img_dir = val_out
                dest_label_dir = val_label_out
                converted_val += 1
            else:
                dest_img_dir = train_out
                dest_label_dir = train_label_out
                converted_train += 1
        
        # Copy image
        dest_img = os.path.join(dest_img_dir, image_filename)
        if not os.path.exists(dest_img):
            os.symlink(os.path.abspath(image_found), dest_img)
        
        # Write YOLO label file
        label_filename = image_filename.rsplit('.', 1)[0] + '.txt'
        label_path = os.path.join(dest_label_dir, label_filename)
        
        with open(label_path, 'w') as f:
            for obj in objects:
                class_id = obj['class_id']
                class_counts[class_id] = class_counts.get(class_id, 0) + 1
                f.write(f"{class_id} {obj['x_center']:.6f} {obj['y_center']:.6f} {obj['width']:.6f} {obj['height']:.6f}\n")
        
        total_images += 1
        
        if total_images % 50 == 0:
            print(f"  Processed {total_images} images...")
    
    print(f"\n{'=' * 60}")
    print(f"Conversion Complete!")
    print(f"  Total images processed: {total_images}")
    print(f"  Train images: {converted_train}")
    print(f"  Val images: {converted_val}")
    print(f"\nClass Distribution:")
    for class_id, count in sorted(class_counts.items()):
        print(f"  {CLASS_NAMES[class_id]}: {count}")
    
    # Create data.yaml for YOLO training
    data_yaml = {
        'path': os.path.abspath(OUTPUT_DIR),
        'train': os.path.join(os.path.abspath(OUTPUT_DIR), 'images', 'train'),
        'val': os.path.join(os.path.abspath(OUTPUT_DIR), 'images', 'val'),
        'nc': len(YOLO_CLASSES),
        'names': [CLASS_NAMES[i] for i in range(len(YOLO_CLASSES))]
    }
    
    data_yaml_path = os.path.join(OUTPUT_DIR, 'data.yaml')
    with open(data_yaml_path, 'w') as f:
        yaml.dump(data_yaml, f, default_flow_style=False)
    
    print(f"\ndata.yaml created at: {data_yaml_path}")
    print(f"YOLO dataset ready at: {OUTPUT_DIR}")
    
    return OUTPUT_DIR

def verify_dataset(dataset_path: str):
    """Verify the converted dataset integrity."""
    print(f"\n{'=' * 60}")
    print("Verifying Dataset Integrity")
    print("=" * 60)
    
    for split in ['train', 'val']:
        img_dir = os.path.join(dataset_path, 'images', split)
        label_dir = os.path.join(dataset_path, 'labels', split)
        
        if not os.path.exists(img_dir):
            print(f"  WARNING: {img_dir} does not exist")
            continue
        
        images = sorted(os.listdir(img_dir))
        labels = sorted(os.listdir(label_dir))
        
        img_bases = set(os.path.splitext(f)[0] for f in images)
        label_bases = set(os.path.splitext(f)[0] for f in labels)
        
        missing_labels = img_bases - label_bases
        missing_images = label_bases - img_bases
        
        print(f"\n{split.upper()} Split:")
        print(f"  Images: {len(images)}")
        print(f"  Labels: {len(labels)}")
        
        if missing_labels:
            print(f"  WARNING: {len(missing_labels)} images missing labels:")
            for m in list(missing_labels)[:5]:
                print(f"    - {m}")
        if missing_images:
            print(f"  WARNING: {len(missing_images)} labels missing images:")
            for m in list(missing_images)[:5]:
                print(f"    - {m}")
        
        # Verify each label file
        total_boxes = 0
        invalid_files = 0
        for label_file in labels:
            label_path = os.path.join(label_dir, label_file)
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) != 5:
                        invalid_files += 1
                        continue
                    total_boxes += 1
        
        print(f"  Total annotations: {total_boxes}")
        if invalid_files:
            print(f"  WARNING: {invalid_files} invalid label files")
    
    print(f"\nDataset verification complete!")

if __name__ == "__main__":
    random.seed(42)
    output_path = convert_dataset()
    verify_dataset(output_path)
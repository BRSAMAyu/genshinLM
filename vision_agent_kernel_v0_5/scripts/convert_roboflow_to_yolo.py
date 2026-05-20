from __future__ import annotations

import argparse
import random
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True, slots=True)
class RemapEntry:
    old_class_id: int
    old_class_name: str
    new_class_id: int


@dataclass(slots=True)
class DatasetStats:
    total_images: int = 0
    train_images: int = 0
    val_images: int = 0
    remapped_labels: int = 0
    skipped_labels: int = 0
    unknown_classes: set[str] = field(default_factory=set)


def load_class_mapping(config_path: Path) -> dict[str, int]:
    import yaml

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    mapping_raw: dict[str, int] = config.get("class_mapping", {})
    return mapping_raw


def build_class_id_mapping(
    input_dir: Path,
    name_to_new_id: dict[str, int],
) -> dict[int, int]:
    yaml_files = list(input_dir.glob("*.yaml")) + list(input_dir.glob("*.yml"))
    data_yaml: Path | None = None
    for yf in yaml_files:
        if "data" in yf.name.lower() or "dataset" in yf.name.lower() or yf.name in (
            "data.yaml",
            "data.yml",
        ):
            data_yaml = yf
            break
    if data_yaml is None and yaml_files:
        data_yaml = yaml_files[0]

    import yaml

    if data_yaml is not None:
        with data_yaml.open("r", encoding="utf-8") as f:
            data_config = yaml.safe_load(f)
        names = data_config.get("names", {})
        id_map: dict[int, int] = {}
        if isinstance(names, dict):
            for idx, name in names.items():
                new_id = name_to_new_id.get(name)
                if new_id is not None:
                    id_map[int(idx)] = new_id
        elif isinstance(names, list):
            for idx, name in enumerate(names):
                new_id = name_to_new_id.get(name)
                if new_id is not None:
                    id_map[idx] = new_id
        return id_map

    classes_file = input_dir / "classes.txt"
    if classes_file.exists():
        lines = classes_file.read_text(encoding="utf-8").strip().splitlines()
        id_map = {}
        for idx, name in enumerate(lines):
            name = name.strip()
            new_id = name_to_new_id.get(name)
            if new_id is not None:
                id_map[idx] = new_id
        return id_map

    print("[convert] warning: no classes file found, using direct name mapping", flush=True)
    return {}


def find_image_label_pairs(input_dir: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []

    search_dirs: list[Path] = []
    for subdir in ("train", "valid", "val", "test", "images", "labels"):
        candidate = input_dir / subdir
        if candidate.is_dir():
            search_dirs.append(candidate)

    if not search_dirs:
        search_dirs = [input_dir]

    image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
    for search_dir in search_dirs:
        for img_file in sorted(search_dir.rglob("*")):
            if img_file.suffix.lower() not in image_extensions:
                continue
            label_file = img_file.with_suffix(".txt")
            if not label_file.exists():
                parent_name = img_file.parent.name.lower()
                if "image" in parent_name:
                    label_parent = img_file.parent.parent / "labels"
                    label_file = label_parent / (img_file.stem + ".txt")
                elif "label" in parent_name:
                    continue
                else:
                    label_file = img_file.with_suffix(".txt")
            pairs.append((img_file, label_file))

    return pairs


def remap_label_file(
    label_path: Path,
    class_id_map: dict[int, int],
    name_to_new_id: dict[str, int],
    stats: DatasetStats,
) -> str | None:
    if not label_path.exists():
        return ""

    lines = label_path.read_text(encoding="utf-8").strip().splitlines()
    remapped: list[str] = []

    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue

        try:
            old_class_id = int(parts[0])
        except ValueError:
            class_name = parts[0]
            new_id = name_to_new_id.get(class_name)
            if new_id is None:
                stats.unknown_classes.add(class_name)
                stats.skipped_labels += 1
                continue
            remapped.append(f"{new_id} " + " ".join(parts[1:]))
            stats.remapped_labels += 1
            continue

        new_id = class_id_map.get(old_class_id)
        if new_id is None:
            stats.skipped_labels += 1
            continue

        remapped.append(f"{new_id} " + " ".join(parts[1:]))
        stats.remapped_labels += 1

    return "\n".join(remapped) if remapped else None


def write_dataset_yaml(output_dir: Path, class_names: dict[int, str]) -> None:
    names_block = "\n".join(f"  {k}: {v}" for k, v in sorted(class_names.items()))
    content = (
        f"path: {output_dir.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "\n"
        f"nc: {len(class_names)}\n"
        "names:\n"
        f"{names_block}\n"
    )
    (output_dir / "dataset.yaml").write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Roboflow-exported dataset to YOLO format with class remapping."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Input directory with Roboflow-exported YOLOv8 dataset",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="datasets/genshin/",
        help="Output directory for converted dataset (default: datasets/genshin/)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/genshin_model.yaml",
        help="Path to genshin_model.yaml with class_mapping (default: configs/genshin_model.yaml)",
    )
    parser.add_argument(
        "--train-split",
        type=float,
        default=0.8,
        help="Train/val split ratio (default: 0.8)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible splits (default: 42)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    config_path = Path(args.config)
    train_split = args.train_split

    if not input_dir.is_dir():
        print(f"[convert] error: input directory not found: {input_dir}", flush=True)
        return 1

    if not config_path.is_file():
        print(f"[convert] error: config file not found: {config_path}", flush=True)
        return 1

    name_to_new_id = load_class_mapping(config_path)
    if not name_to_new_id:
        print("[convert] error: no class_mapping found in config", flush=True)
        return 1

    print(f"[convert] loaded {len(name_to_new_id)} class mappings", flush=True)

    class_id_map = build_class_id_mapping(input_dir, name_to_new_id)
    print(f"[convert] resolved {len(class_id_map)} class ID mappings", flush=True)

    train_img_dir = output_dir / "images" / "train"
    val_img_dir = output_dir / "images" / "val"
    train_lbl_dir = output_dir / "labels" / "train"
    val_lbl_dir = output_dir / "labels" / "val"
    for d in (train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir):
        d.mkdir(parents=True, exist_ok=True)

    pairs = find_image_label_pairs(input_dir)
    if not pairs:
        print("[convert] error: no image/label pairs found in input directory", flush=True)
        return 1

    print(f"[convert] found {len(pairs)} image/label pairs", flush=True)

    random.seed(args.seed)
    indices = list(range(len(pairs)))
    random.shuffle(indices)
    split_point = int(len(indices) * train_split)
    train_indices = set(indices[:split_point])

    class_names: dict[int, str] = {
        0: "monster_normal",
        1: "monster_elite",
        2: "monster_boss",
        3: "ore",
        4: "plant",
        5: "chest",
        6: "loot_beam",
        7: "interaction_prompt",
        8: "hp_bar_enemy",
        9: "danger_zone",
    }

    stats = DatasetStats()

    for idx, (img_path, lbl_path) in enumerate(pairs):
        is_train = idx in train_indices
        target_img_dir = train_img_dir if is_train else val_img_dir
        target_lbl_dir = train_lbl_dir if is_train else val_lbl_dir

        dest_img = target_img_dir / img_path.name
        shutil.copy2(img_path, dest_img)

        remapped = remap_label_file(lbl_path, class_id_map, name_to_new_id, stats)
        dest_lbl = target_lbl_dir / (img_path.stem + ".txt")
        if remapped is not None:
            dest_lbl.write_text(remapped + "\n", encoding="utf-8")
        elif remapped == "":
            dest_lbl.write_text("", encoding="utf-8")
        else:
            dest_lbl.write_text("", encoding="utf-8")

        if is_train:
            stats.train_images += 1
        else:
            stats.val_images += 1
        stats.total_images += 1

    write_dataset_yaml(output_dir, class_names)

    print(
        f"[convert] done: total={stats.total_images} "
        f"train={stats.train_images} val={stats.val_images} "
        f"remapped_labels={stats.remapped_labels} "
        f"skipped_labels={stats.skipped_labels}",
        flush=True,
    )
    if stats.unknown_classes:
        unknown_list = sorted(stats.unknown_classes)
        print(
            f"[convert] warning: {len(unknown_list)} unknown classes skipped: "
            f"{unknown_list[:20]}{'...' if len(unknown_list) > 20 else ''}",
            flush=True,
        )

    print(f"[convert] dataset.yaml written to {output_dir / 'dataset.yaml'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

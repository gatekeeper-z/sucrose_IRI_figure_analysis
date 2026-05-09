from pathlib import Path

from iri_analyzer.io import load_config, validate_config
from iri_analyzer.pipeline import run_qc


def main() -> None:
    config = load_config()
    validate_config(config)
    run_qc(Path("path/to/image.bmp"), Path("output_dir"), config, overwrite=True)


if __name__ == "__main__":
    main()

# ml

Anomaly-detection research on the GAIA dataset. Nothing here runs in the incident pipeline yet; the trained
LightGBM model is loaded by the backend only through `check_for_anomaly_trigger`.

```
ml/
├── data_loaders/   GAIA business / metric / trace loaders and the fault-window ground truth (import as ml.data_loaders)
├── experiments/    The training scripts, in the order they were developed:
│                   run_eda -> run_feature_engineering -> run_baseline_model -> run_autoencoder_model / _v2
│                   -> run_lightgbm_classifier -> _tuned -> _final -> run_precision_optimized
│                   -> run_ensemble_calibrated -> run_pruning_cv
├── tools/          One-off GAIA inspection scripts
├── tests/          Loader tests (run with the rest: python -m pytest -m "not live")
├── models/         Trained artifacts (git-ignored; the folder is kept by .gitkeep)
├── reports/        Generated figures, for example the EDA plot
└── requirements.txt  Extra libraries for the experiments (matplotlib, xgboost, py7zr)
```

## Run an experiment

From the repository root, with `pip install -r ml/requirements.txt`:

```powershell
python ml/experiments/run_lightgbm_final.py
```

Scripts read the datasets from `data/` (git-ignored; `data/processed/gaia_unified.parquet` and
`data/model_inputs/`), write models to `ml/models/`, and log runs to `mlflow.db` at the repository root
(artifacts under `mlruns/`). Set `MLFLOW_TRACKING_URI` to log somewhere else, for example DagsHub.
Browse runs with `mlflow ui --backend-store-uri sqlite:///mlflow.db`.

## Current model

`ml/models/lightgbm_final_classifier.joblib` (37 features): test F1 0.776, precision 0.727, recall 0.899,
AUC 0.953. It knows only GAIA's service names, so it cannot score Online Boutique services directly.

param(
    [int]$Port = 7860
)

python -m uvicorn idpo.ui.app:app --host 0.0.0.0 --port $Port

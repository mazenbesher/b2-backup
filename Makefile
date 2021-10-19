LOGFILE = logs/$(shell date --iso=seconds).txt

sync:
	. venv/bin/activate; \
	python main.py sync --verbose | tee $(LOGFILE); \

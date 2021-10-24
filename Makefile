sync:
	. venv/bin/activate; \
	python main.py sync --verbose | tee logs/$(shell date --iso=seconds).txt; \

size:
	. venv/bin/activate; \
	python main.py compute-backup-size --show-files --show-largest-files 10 \

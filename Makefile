clean:
	rm -rf dist build *.egg-info

dist:	clean
	python setup.py sdist bdist_wheel

upload:
	twine upload dist/*

.PHONY: dist upload test
Create Python Virtual Env

mkdir pycode
cd pycode

python3 -m venv .venv

source .venv/bin/activate

pip install pandas
pip install pytest

pip install --upgrade pip

pip freeze > requirements.txt
cat requirements.txt

pip install -r requirements.txt

deactivate
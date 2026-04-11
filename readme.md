Create Python Virtual Env
mkdir pycode
cd pycode
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
cat requirements.txt
pip install -r requirements.txt
pip freeze > requirements.txt
deactivate

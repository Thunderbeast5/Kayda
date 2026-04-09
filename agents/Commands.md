# Option 1 - One Command (Mac/Linux):
chmod +x start.sh
./start.sh

# Option 2 - Windows:
start.bat

# Option 3 - Manual:
Terminal 1
npm run dev

Terminal 2  
cd agents
Only one time: python -m venv venv

Then run this every time for activating venv:
macOS/Linux:
source venv/bin/activate

Windows (PowerShell):
venv\Scripts\Activate.ps1

Windows (Command Prompt):
venv\Scripts\activate.bat

pip install -r requirements.txt
python server.py
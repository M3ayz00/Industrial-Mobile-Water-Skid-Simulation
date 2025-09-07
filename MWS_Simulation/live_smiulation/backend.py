#!/usr/bin/env python3
"""
Flask Backend for Water Treatment PLC Web Interface
Connects the web frontend to OpenPLC via Modbus
"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
import json
from datetime import datetime

# Import our PLC controller
try:
    from pymodbus.client import ModbusTcpClient
    PYMODBUS_VERSION = 3
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient
    PYMODBUS_VERSION = 2

app = Flask(__name__)
app.config['SECRET_KEY'] = 'plc_secret_key_2024'
socketio = SocketIO(app, cors_allowed_origins="*")

class PLCWebController:
    def __init__(self, host='localhost', port=502):
        self.host = host
        self.port = port
        self.client = ModbusTcpClient(host, port=port)
        self.connected = False
        self.monitoring = False
        self.monitor_thread = None
        self.last_data = {}
        
        # Phase 1 - Direct I/O Coils
        self.coil_map = {
            'pump': 0,              # %QX0.0
            'filter': 1,            # %QX0.1
            'uv_reactor': 2,        # %QX0.2
            'start_button': 3,      # %QX0.3
            'emergency_button': 4,  # %QX0.4
            'low_level_sensor': 5,  # %QX0.5
            'green_light': 6,       # %QX0.6
            'orange_light': 7,      # %QX0.7
            'red_light': 8,         # %QX1.0
            'fault_light': 9,       # %QX1.1
            'pt_alert': 10,         # %QX1.2
            'ft_alert': 11,         # %QX1.3
            'turbidity_alert': 12,  # %QX1.4
            
            # Phase 2 - Simulation Control Coils
            'pt_inc_sim': 16,       # %QX2.0
            'pt_dec_sim': 17,       # %QX2.1
            'ft_inc_sim': 18,       # %QX2.2
            'ft_dec_sim': 19,       # %QX2.3
            'turb_inc_sim': 20,     # %QX2.4
            'turb_dec_sim': 21,     # %QX2.5
            'level_inc_sim': 22,    # %QX2.6
            'level_dec_sim': 23,    # %QX2.7
        }
        
        # Phase 2 - Memory Registers
        self.register_map = {
            'pressure_value': 0,    # %MW0
            'flow_value': 1,        # %MW1
            'turbidity_value': 2,   # %MW2
            'water_level': 3,       # %MW3
        }
        
        # Thresholds
        self.thresholds = {
            'pt_low': 20,
            'pt_high': 80,
            'ft_low': 10,
            'turb_high': 15,
            'level_low': 20
        }
    
    def connect(self):
        """Connect to PLC"""
        try:
            if PYMODBUS_VERSION >= 3:
                self.connected = True
            else:
                self.connected = self.client.connect()
            
            if self.connected:
                print(f"✅ PLC Backend connected to {self.host}:{self.port}")
                # Test connection
                try:
                    result = self.client.read_coils(0, 1)
                    if hasattr(result, 'isError') and result.isError():
                        print("⚠️ PLC not responding - check OpenPLC")
                        return True  # Still allow connection for demo
                    print("✅ OpenPLC is responding")
                except Exception as e:
                    print(f"⚠️ Could not test PLC: {e}")
                return True
            else:
                print("❌ Failed to connect to PLC")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from PLC"""
        if self.connected:
            self.stop_monitoring()
            if PYMODBUS_VERSION < 3 and hasattr(self.client, 'close'):
                self.client.close()
            self.connected = False
            print("🔌 Disconnected from PLC")
    
    def write_coil(self, name, value):
        """Write to a coil by name"""
        if not self.connected:
            return False
        
        if name not in self.coil_map:
            print(f"❌ Unknown coil: {name}")
            return False
        
        try:
            address = self.coil_map[name]
            result = self.client.write_coil(address, value)
            
            if hasattr(result, 'isError') and result.isError():
                print(f"❌ Error writing coil {name}: {result}")
                return False
            
            print(f"📤 {name} = {value}")
            return True
        except Exception as e:
            print(f"❌ Error writing coil {name}: {e}")
            return False
    
    def read_coils(self, count=24):
        """Read all coils"""
        if not self.connected:
            return {}
        
        try:
            result = self.client.read_coils(0, count)
            
            if hasattr(result, 'isError') and result.isError():
                return {}
            
            coil_status = {}
            bits = result.bits if hasattr(result, 'bits') else result
            
            for name, address in self.coil_map.items():
                if address < len(bits):
                    coil_status[name] = bits[address]
            return coil_status
        except Exception as e:
            print(f"❌ Error reading coils: {e}")
            return {}
    
    def read_registers(self):
        """Read all memory registers"""
        if not self.connected:
            return {}
        
        try:
            result = self.client.read_holding_registers(0, 4)
            
            if hasattr(result, 'isError') and result.isError():
                return {}
            
            register_values = {}
            registers = result.registers if hasattr(result, 'registers') else result
            
            for name, address in self.register_map.items():
                if address < len(registers):
                    register_values[name] = registers[address]
            return register_values
        except Exception as e:
            print(f"❌ Error reading registers: {e}")
            return {}
    
    def pulse_coil(self, name, duration=0.1):
        """Send a pulse to a coil"""
        if self.write_coil(name, True):
            time.sleep(duration)
            self.write_coil(name, False)
            return True
        return False
    
    def adjust_parameter(self, param, direction, steps=1):
        """Adjust analog parameter"""
        param_map = {
            'pressure': ('pt_inc_sim', 'pt_dec_sim'),
            'flow': ('ft_inc_sim', 'ft_dec_sim'),
            'turbidity': ('turb_inc_sim', 'turb_dec_sim'),
            'level': ('level_inc_sim', 'level_dec_sim')
        }
        
        if param not in param_map:
            return False
        
        inc_coil, dec_coil = param_map[param]
        coil = inc_coil if direction == 'up' else dec_coil
        
        for _ in range(steps):
            self.pulse_coil(coil, 0.1)
            time.sleep(0.1)
        
        return True
    
    def get_system_data(self):
        """Get complete system data"""
        coils = self.read_coils()
        registers = self.read_registers()
        
        # Calculate alerts based on thresholds
        alerts = []
        if registers.get('pressure_value', 50) < self.thresholds['pt_low'] or \
           registers.get('pressure_value', 50) > self.thresholds['pt_high']:
            alerts.append('Pressure Alert')
        
        if registers.get('flow_value', 25) < self.thresholds['ft_low']:
            alerts.append('Flow Alert')
            
        if registers.get('turbidity_value', 5) > self.thresholds['turb_high']:
            alerts.append('Turbidity Alert')
            
        if registers.get('water_level', 75) < self.thresholds['level_low']:
            alerts.append('Low Level Alert')
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'connected': self.connected,
            'coils': coils,
            'registers': registers,
            'alerts': alerts,
            'system_fault': len(alerts) > 0
        }
        
        self.last_data = data
        return data
    
    def start_monitoring(self):
        """Start monitoring thread"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        print("📊 Started PLC monitoring")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=1)
            print("⏹️ Stopped PLC monitoring")
    
    def _monitor_loop(self):
        """Monitoring loop"""
        while self.monitoring and self.connected:
            try:
                data = self.get_system_data()
                # Emit data to all connected web clients
                socketio.emit('plc_data', data)
                time.sleep(1)  # Update every second
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                time.sleep(2)

# Global PLC controller instance
plc_controller = None

# Flask Routes
@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('dashboard.html')

@app.route('/api/connect', methods=['POST'])
def connect_plc():
    """Connect to PLC"""
    global plc_controller
    
    data = request.get_json()
    host = data.get('host', 'localhost')
    port = data.get('port', 502)
    
    try:
        if plc_controller:
            plc_controller.disconnect()
        
        plc_controller = PLCWebController(host, port)
        
        if plc_controller.connect():
            plc_controller.start_monitoring()
            return jsonify({'success': True, 'message': 'Connected to PLC'})
        else:
            return jsonify({'success': False, 'message': 'Failed to connect to PLC'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/disconnect', methods=['POST'])
def disconnect_plc():
    """Disconnect from PLC"""
    global plc_controller
    
    if plc_controller:
        plc_controller.disconnect()
        plc_controller = None
    
    return jsonify({'success': True, 'message': 'Disconnected from PLC'})

@app.route('/api/system_data')
def get_system_data():
    """Get current system data"""
    if plc_controller and plc_controller.connected:
        return jsonify(plc_controller.get_system_data())
    else:
        return jsonify({'error': 'PLC not connected'}), 400

@app.route('/api/control', methods=['POST'])
def control_system():
    """Control system operations"""
    if not plc_controller or not plc_controller.connected:
        return jsonify({'success': False, 'message': 'PLC not connected'}), 400
    
    data = request.get_json()
    action = data.get('action')
    
    try:
        if action == 'start':
            success = plc_controller.pulse_coil('start_button')
        elif action == 'emergency_stop':
            success = plc_controller.write_coil('emergency_button', True)
        elif action == 'reset':
            success = plc_controller.write_coil('emergency_button', False)
        elif action == 'adjust_parameter':
            param = data.get('parameter')
            direction = data.get('direction')
            steps = data.get('steps', 1)
            success = plc_controller.adjust_parameter(param, direction, steps)
        elif action == 'scenario':
            success = run_scenario(data.get('scenario'))
        else:
            return jsonify({'success': False, 'message': 'Unknown action'})
        
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def run_scenario(scenario):
    """Run predefined test scenarios"""
    if not plc_controller:
        return False
    
    try:
        if scenario == 'normal_startup':
            # Reset to normal values
            plc_controller.write_coil('emergency_button', False)
            time.sleep(0.5)
            # Set normal parameter values (this would need multiple adjustments in real implementation)
            plc_controller.pulse_coil('start_button')
            
        elif scenario == 'low_pressure':
            # Simulate low pressure by adjusting down multiple times
            for _ in range(8):  # Reduce pressure from ~50 to ~10
                plc_controller.pulse_coil('pt_dec_sim', 0.1)
                time.sleep(0.1)
                
        elif scenario == 'high_turbidity':
            # Simulate high turbidity
            for _ in range(8):  # Increase turbidity to > 15
                plc_controller.pulse_coil('turb_inc_sim', 0.1)
                time.sleep(0.1)
                
        elif scenario == 'multiple_faults':
            # Create multiple faults
            for _ in range(8):  # Low pressure
                plc_controller.pulse_coil('pt_dec_sim', 0.1)
                time.sleep(0.05)
            for _ in range(6):  # Low flow  
                plc_controller.pulse_coil('ft_dec_sim', 0.1)
                time.sleep(0.05)
            for _ in range(10):  # High turbidity
                plc_controller.pulse_coil('turb_inc_sim', 0.1)
                time.sleep(0.05)
        else:
            return False
        
        return True
    except Exception as e:
        print(f"❌ Scenario error: {e}")
        return False

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('🔌 Web client connected')
    if plc_controller and plc_controller.last_data:
        emit('plc_data', plc_controller.last_data)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('🔌 Web client disconnected')

@socketio.on('plc_command')
def handle_plc_command(data):
    """Handle commands from web interface"""
    if not plc_controller or not plc_controller.connected:
        emit('error', {'message': 'PLC not connected'})
        return
    
    try:
        command = data.get('command')
        
        if command == 'start_system':
            plc_controller.pulse_coil('start_button')
        elif command == 'emergency_stop':
            plc_controller.write_coil('emergency_button', True)
        elif command == 'reset_system':
            plc_controller.write_coil('emergency_button', False)
        elif command == 'adjust_parameter':
            param = data.get('parameter')
            direction = data.get('direction')
            plc_controller.adjust_parameter(param, direction)
        
        emit('command_result', {'success': True})
        
    except Exception as e:
        emit('command_result', {'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("🏭 Water Treatment PLC Web Server")
    print("="*40)
    
    # Try to connect to default PLC
    plc_controller = PLCWebController('localhost', 502)
    if plc_controller.connect():
        plc_controller.start_monitoring()
        print("✅ Auto-connected to OpenPLC on localhost:502")
    else:
        print("⚠️ Could not auto-connect to PLC. Use web interface to connect.")
    
    try:
        print("\n🌐 Starting web server...")
        print("📱 Open your browser to: http://localhost:5000")
        print("🛑 Press Ctrl+C to stop\n")
        
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        if plc_controller:
            plc_controller.disconnect()
    finally:
        print("✅ Server stopped")
import re
import shutil
import subprocess

# this machine's health, shown by the diagnostics page and the web remote


async def _get_cpu_temperature():
    """Get CPU temperature using various methods depending on the system"""
    
    # Method 1: Raspberry Pi vcgencmd (original method)
    if shutil.which("vcgencmd"):
        try:
            result = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
            # output in form: temp=49.4'C
            temp_c = float(result.split("=")[1].split("'")[0])
            temp_f = round((temp_c * 1.8) + 32)
            return {
                "temperature_c": round(temp_c, 1),
                "temperature_f": temp_f,
                "temp_source": "vcgencmd"
            }
        except Exception:
            pass
    
    # Method 2: Linux thermal zones (most modern Linux systems)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_millicelsius = int(f.read().strip())
            temp_c = temp_millicelsius / 1000.0
            temp_f = round((temp_c * 1.8) + 32)
            return {
                "temperature_c": round(temp_c, 1),
                "temperature_f": temp_f,
                "temp_source": "thermal_zone"
            }
    except Exception:
        pass
    
    # Method 3: Using lm-sensors (if available)
    if shutil.which("sensors"):
        try:
            result = subprocess.check_output(["sensors"], text=True)
            # Look for CPU temperature in sensors output
            for line in result.split('\n'):
                if 'Core 0' in line or 'CPU' in line or 'temp1' in line:
                    match = re.search(r'([+-]?\d+\.?\d*)\s*°C', line)
                    if match:
                        temp_c = float(match.group(1))
                        temp_f = round((temp_c * 1.8) + 32)
                        return {
                            "temperature_c": round(temp_c, 1),
                            "temperature_f": temp_f,
                            "temp_source": "sensors"
                        }
        except Exception:
            pass
    
    return {"temperature": "unavailable"}


async def _get_memory_info():
    """Get memory information from /proc/meminfo"""
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        
        # Parse meminfo
        mem_total = 0
        mem_available = 0
        mem_free = 0
        
        for line in meminfo.split('\n'):
            if 'MemTotal:' in line:
                mem_total = int(line.split()[1]) * 1024  # Convert from KB to bytes
            elif 'MemAvailable:' in line:
                mem_available = int(line.split()[1]) * 1024
            elif 'MemFree:' in line:
                mem_free = int(line.split()[1]) * 1024
        
        # Use MemAvailable if available, otherwise fall back to MemFree
        available = mem_available if mem_available > 0 else mem_free
        used = mem_total - available
        used_percent = round((used / mem_total) * 100, 1) if mem_total > 0 else 0
        
        return {
            "memory": {
                "total_gb": round(mem_total / (1024**3), 1),
                "available_gb": round(available / (1024**3), 1),
                "used_gb": round(used / (1024**3), 1),
                "used_percent": used_percent
            }
        }
    except Exception:
        return {"memory": {"error": "unavailable"}}


async def _get_cpu_info():
    """Get CPU usage information"""
    try:
        # Get CPU count
        cpu_count = 0
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
            cpu_count = cpuinfo.count("processor")
        except Exception:
            cpu_count = 1
        
        # Get load average (simpler than trying to calculate CPU percentage)
        try:
            with open("/proc/loadavg", "r") as f:
                loadavg = f.read().strip().split()
            load_1min = float(loadavg[0])
            load_5min = float(loadavg[1])
            load_15min = float(loadavg[2])
            
            # Convert load to rough percentage (load/cores * 100)
            load_percent = round((load_1min / cpu_count) * 100, 1) if cpu_count > 0 else 0
            
            return {
                "cpu": {
                    "cores": cpu_count,
                    "load_1min": load_1min,
                    "load_5min": load_5min,
                    "load_15min": load_15min,
                    "load_percent": load_percent
                }
            }
        except Exception:
            return {
                "cpu": {
                    "cores": cpu_count,
                    "load": "unavailable"
                }
            }
    except Exception:
        return {"cpu": {"error": "unavailable"}}


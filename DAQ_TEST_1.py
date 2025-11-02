#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct  12 21:24:55 2025

@author: X-51
"""

import pyvisa
import nidaqmx
import uuid
import time
from datetime import datetime
import pypyodbc as odbc
import sys


class SMUController:
    """SMU configuration and control"""
    
    def __init__(self, resource_name='TCPIP0::10.0.0.38::5025::SOCKET'):
        self.resource_name = resource_name
        self.instrument = None
        self.rm = None
    
    def connect(self):
        """Connect to the SMU instrument"""
        try:
            self.rm = pyvisa.ResourceManager()
            self.instrument = self.rm.open_resource(self.resource_name)
            self.instrument.timeout = 10000
            self.instrument.read_termination = '\n'
            self.instrument.write_termination = '\n'
            
            idn = self.instrument.query('*IDN?')
            print(f" Connected to SMU: {idn}")
            return True
        except Exception as e:
            print(f"SMU Connection Error: {e}")
            return False
    
    def configure(self, current=0.0001, current_range=0.001, voltage_limit=2.5):
        """Configure SMU as current source"""
        try:
            # Initialize
            self.instrument.write(':SYST:CLE')
            self.instrument.write('*RST')
            time.sleep(1)
            
            # Setup current source
            self.instrument.write(':SOUR:FUNC CURR')
            self.instrument.write(f':SOUR:CURR:RANG {current_range}')
            self.instrument.write(f':SOUR:CURR:VLIM {voltage_limit}')
            self.instrument.write(f':SOUR:CURR {current}')
            self.instrument.write(':SENS:FUNC "VOLT"')
            
           
            return True
        except Exception as e:
            print(f"SMU Configuration Error: {e}")
            return False
    
    def turn_on(self):
        """Turn on SMU output"""
        try:
            self.instrument.write(':OUTP ON')
            self.instrument.write(':INIT')
            print("SMU Output: ON")
            return True
        except Exception as e:
            print(f"SMU Turn On Error: {e}")
            return False
    
    def turn_off(self):
        """Turn off SMU output"""
        try:
            if self.instrument is not None:
                self.instrument.write(':OUTP OFF')
                print("SMU Output: OFF")
        except Exception as e:
            print(f"SMU Turn Off Error: {e}")
    
    def close(self):
        """Close SMU connection"""
        try:
            self.turn_off()
            if self.instrument is not None:
                self.instrument.close()
                print("SMU Connection closed")
        except Exception as e:
            print(f"Error closing SMU: {e}")


class DatabaseManager:
    """SQL Server database operations"""
    
    def __init__(self, server='VOLT-001', database='X51'):
        self.server = server
        self.database = database
        self.driver = 'SQL Server'
    
    def _get_connection(self):
        """Create and return database connection"""
        conn_string = f"""
        Driver={{{self.driver}}};
        Server={{{self.server}}};
        Database={{{self.database}}};
        Trusted_Connection=yes;
        """
        try:
            conn = odbc.connect(conn_string)
            return conn
        except Exception as e:
            print(f"Database Connection Error: {e}")
            return None
    
    def insert_data(self, value, table_name):
        """Insert data into specified table"""
        conn = self._get_connection()
        if conn is None:
            return False
        
        try:
            cursor = conn.cursor()
            
            # Different insert statements based on table
            if table_name in ['TEST_1', 'TAB_2', 'TAB_3']:
                insert_statement = f"INSERT INTO {table_name} VALUES(?,?,?,?)"
            elif table_name == 'TAB_1':
                insert_statement = f"INSERT INTO {table_name} VALUES(?,?,?)"
            else:
                print(f"Unknown table: {table_name}")
                return False
            
            for record in value:
                cursor.execute(insert_statement, record)
            
            conn.commit()
            
            return True
            
        except Exception as e:
            print(f" Database Insert Error ({table_name}): {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()


class DAQReader:
    """Class to handle NI-DAQ data acquisition"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.run_id = str(uuid.uuid4())[:5]
        """print(f"Run ID: {self.run_id}")"""
    
    def read_channel(self, channel_name, table_name, num_samples=2000):
        """Read data from specified DAQ channel """
        task = None
        try:
            # Create and start DAQ task
            task = nidaqmx.Task()
            task.ai_channels.add_ai_voltage_chan(channel_name)
            task.start()
            
            print(f"\n→ Reading {channel_name} → {table_name}")
            
            start_time = None
            stop_time = None
            
            
            for i in range(num_samples):
                voltage = task.read()
                voltage_rounded = round(voltage, 3)
                timestamp = datetime.now().time().strftime('%H:%M:%S.%f')
                date_str = datetime.now().date().strftime('%Y-%m-%d')
                
                if i == 0:
                    start_time = timestamp
                if i == (num_samples - 1):
                    stop_time = timestamp
                
               
                value = [[self.run_id, voltage_rounded, timestamp, date_str]]
                success = self.db_manager.insert_data(value, table_name)
                
                if not success:
                    print(f"Failed to insert data for {channel_name}")
                    return False
            
            # Insert metadata
            metadata = [[self.run_id, start_time, stop_time]]
            self.db_manager.insert_data(metadata, 'TAB_1')
            
            print(f"Completed {channel_name}: {num_samples} samples")
            return True
            
        except nidaqmx.DaqError as e:
            print(f"DAQ Error on {channel_name}: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error on {channel_name}: {e}")
            return False
        finally:
            if task is not None:
                try:
                    task.stop()
                    task.close()
                except:
                    pass


def main():
    """Main execution function"""
    
   
    smu = SMUController()
    db = DatabaseManager()
    daq = DAQReader(db)
    
    try:
        
        if not smu.connect():
            print("Failed to connect to SMU. Exiting.")
            return
        
        if not smu.configure(current=0.0001, current_range=0.001, voltage_limit=2.5):
            print("Failed to configure SMU. Exiting.")
            return
        
        if not smu.turn_on():
            print("Failed to turn on SMU. Exiting.")
            return
        
        
        cycle = 1
        while True:
            
            
            if not daq.read_channel("Dev1/ai0", "TEST_1", num_samples=2000):
                print("Failed at Dev1/ai0. Exiting...")
                break
            time.sleep(2)
            
            
            if not daq.read_channel("Dev1/ai1", "TAB_2", num_samples=2000):
                print("Failed at Dev1/ai1. Exiting...")
                break
            time.sleep(2)
            
            
            if not daq.read_channel("Dev1/ai2", "TAB_3", num_samples=2000):
                print("Failed at Dev1/ai2. Exiting...")
                break
            
            
            time.sleep(600)  # 10 minutes
            cycle += 1
    
    except KeyboardInterrupt:
        print("\n\n⚠ Program interrupted by user (Ctrl+C)")
    
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
    
    finally:
        
        print("SHUTDOWN SEQUENCE")
        smu.close()
        print("\n✓ System shutdown complete")


if __name__ == "__main__":
    main()

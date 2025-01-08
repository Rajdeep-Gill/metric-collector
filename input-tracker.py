from pynput import mouse, keyboard
import os
from dataclasses import dataclass
from threading import Thread
import psycopg2
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# --- Constants ---
SPECIAL_KEYS = {
    'shift', 'shift_r', 'shift_l', 'ctrl', 'ctrl_r', 'ctrl_l',
    'alt', 'alt_r', 'alt_l', 'cmd', 'cmd_r', 'cmd_l',
    'enter', 'backspace', 'delete', 'space', 'tab', 'caps_lock',
    'esc', 'up', 'down', 'left', 'right',
    'page_up', 'page_down', 'home', 'end',
    'insert', 'num_lock', 'scroll_lock',
    'f1', 'f2', 'f3', 'f4', 'f5', 'f6',
    'f7', 'f8', 'f9', 'f10', 'f11', 'f12'
}

REGULAR_KEYS = {
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j',
    'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't',
    'u', 'v', 'w', 'x', 'y', 'z',
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    '`', '-', '=', '[', ']', '\\', ';', "'", ',', '.', '/',
    '~', '!', '@', '#', '$', '%', '^', '&', '*', '(', ')',
    '_', '+', '{', '}', '|', ':', '"', '<', '>', '?'
}

MOUSE_BUTTONS = {'mouse_left', 'mouse_right', 'mouse_middle'}
ALL_INPUTS = SPECIAL_KEYS.union(REGULAR_KEYS).union(MOUSE_BUTTONS)

# --- Data Class ---
@dataclass
class Metrics:
  input_counts: dict = None
  last_updated: str = None
  
  def __str__(self):
      mouse_stats = (
          f'Mouse Clicks - '
          f'L: [{self.input_counts.get("mouse_left", 0)}] '
          f'R: [{self.input_counts.get("mouse_right", 0)}] '
          f'M: [{self.input_counts.get("mouse_middle", 0)}]'
      )
      key_stats = f'Total key presses: {sum(count for key, count in self.input_counts.items() if not key.startswith("mouse_"))}'
      return f'{mouse_stats}\n{key_stats}\nLast updated: {self.last_updated}'
    
class Database:
  def __init__(self):
    self.conn = None
    self.cur = None
    
  def connect(self):
    self.conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    self.cur = self.conn.cursor()
    
  def disconnect(self):
    if self.cur:
      self.cur.close()
    if self.conn:
      self.conn.close()
      
  def setup_database(self):
    self.connect()
    self.cur.execute(
      """
        CREATE TABLE IF NOT EXISTS key_presses (
            input_name TEXT PRIMARY KEY,
            press_count INTEGER DEFAULT 0,
            last_updated TIMESTAMP
        );
      """
    )    
    self.conn.commit()

  def load_data(self):
    self.connect()
    self.cur.execute("SELECT input_name, press_count FROM key_presses")
    data= {row[0]: row[1] for row in self.cur.fetchall()}
    self.disconnect()
    return data
  
  def save_data(self, data: Metrics):
    self.connect()
    data.last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for input_name, press_count in data.input_counts.items():
      self.cur.execute("""
          INSERT INTO key_presses (input_name, press_count, last_updated)
          VALUES (%s, %s, %s)
          ON CONFLICT (input_name) DO UPDATE 
          SET 
              press_count = EXCLUDED.press_count,
              last_updated = EXCLUDED.last_updated
      """, (input_name, press_count, data.last_updated))
      
    self.conn.commit()
    self._print_current_counts()

    self.disconnect()  
    
  def _initialize_inputs(self):
    for id in ALL_INPUTS:
      self.cur.execute(
        """
          INSERT INTO key_presses (input_name, press_count, last_updated)
          VALUES (%s, 0, NOW())
          ON CONFLICT (input_name) DO NOTHING
        """, (id,)
      )
    self.conn.commit()
    
  def _print_current_counts(self):
    self.cur.execute("""
        SELECT input_name, press_count, last_updated 
        FROM key_presses 
        WHERE press_count > 0
        ORDER BY press_count DESC
    """)
    print("\nCurrent Input Counts:")
    for row in self.cur.fetchall():
        print(f"Input: {row[0]}, Count: {row[1]}, Last Updated: {row[2]}")


# --- Main ---
def main():
  metrics = Metrics()
  metrics.input_counts = {key: 0 for key in ALL_INPUTS}
  db = Database()
  save_interval = 5  # seconds
  
  # Setup database
  db.setup_database()
  db._initialize_inputs()
  
  # Load previous data
  previous_data = db.load_data()
  metrics.input_counts.update(previous_data)
  
  # Save metrics every interval
  def save_metrics():
    while True:
      time.sleep(save_interval)
      db.save_data(metrics)  
      
  save_thread = Thread(target=save_metrics)
  save_thread.daemon = True
  save_thread.start()
  
  # Start tracking inputs
  def on_press(key):
    key_str = key.char if hasattr(key, 'char') else str(key).replace('Key.', '')
    if key_str in metrics.input_counts:
      metrics.input_counts[key_str] += 1
    else:
      print(f'Unknown key: {key_str}')
      
    if key == keyboard.Key.esc:
      print("Stopping program...")
      print("Total metrics for the current session: ", metrics)
      # Save final metrics before exiting
      db.save_data(metrics)
      os._exit(0)

      
  def on_click(x, y, button, pressed):
    if pressed:
      if button == mouse.Button.left:
        metrics.input_counts['mouse_left'] += 1
      elif button == mouse.Button.right:
        metrics.input_counts['mouse_right'] += 1
      elif button == mouse.Button.middle:
        metrics.input_counts['mouse_middle'] += 1
      
  with mouse.Listener(on_click=on_click) as mouse_listener:
    with keyboard.Listener(on_press=on_press) as key_listener:
      mouse_listener.join()
      key_listener.join()

if __name__ == '__main__':
  main()
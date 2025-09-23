#!/usr/bin/env python3
"""
F1 Leaderboard Display for Raspberry Pi + Waveshare 2.13" e-Paper
Description: Two-screen F1 dashboard showing live standings and next race info with real OpenF1 API integration
"""

import time
import requests
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont
import json
import math
from typing import Dict, List, Optional, Tuple

# Comment out the following lines if testing without the actual e-paper display
try:
    import sys
    import os
    picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
    libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
    if os.path.exists(libdir):
        sys.path.append(libdir)
    from waveshare_epd import epd2in13_V2
    HAS_EPAPER = True
except ImportError:
    HAS_EPAPER = False
    print("Warning: Waveshare e-paper library not found. Running in simulation mode.")

class F1LeaderboardDisplay:
    def __init__(self):
        # Display configuration
        self.width = 250
        self.height = 122
        self.current_screen = 0  # 0 = leaderboard, 1 = track
        
        # Initialize e-paper display if available
        if HAS_EPAPER:
            self.epd = epd2in13_V2.EPD()
            self.epd.init()
            self.epd.Clear(0xFF)
        
        # Try to load fonts (fallback to default if not available)
        try:
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
            self.font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        except OSError:
            print("Custom fonts not found, using default fonts")
            self.font_small = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_large = ImageFont.load_default()
        
        # Data cache
        self.drivers_data = []
        self.constructors_data = []
        self.next_race_data = None
        self.track_coordinates = []
        self.last_update = 0
        
        # Team name abbreviations for display
        self.team_abbreviations = {
            'Red Bull Racing': 'RED BULL',
            'Mercedes': 'MERCEDES',
            'Aston Martin': 'ASTON MARTIN',
            'Ferrari': 'FERRARI',
            'McLaren': 'MCLAREN',
            'Alpine': 'ALPINE',
            'Williams': 'WILLIAMS',
            'AlphaTauri': 'ALPHATAURI',
            'Alfa Romeo': 'ALFA ROMEO',
            'Haas': 'HAAS'
        }

    def get_current_season_data(self) -> Tuple[Optional[str], Optional[str]]:
        """Get the latest session key and meeting key for current season standings"""
        try:
            current_year = datetime.now().year
            # Get the latest completed race session
            sessions_url = f"https://api.openf1.org/v1/sessions?year={current_year}&session_name=Race"
            
            response = requests.get(sessions_url, timeout=10)
            if response.status_code == 200:
                sessions = response.json()
                if sessions:
                    # Get the most recent race session
                    latest_session = max(sessions, key=lambda x: x['date_start'])
                    return latest_session['session_key'], latest_session['meeting_key']
            
            return None, None
            
        except Exception as e:
            print(f"Error getting season data: {e}")
            return None, None

    def calculate_championship_standings(self, session_results: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Calculate championship standings from session results"""
        # Points system for F1
        points_system = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
        
        driver_points = {}
        constructor_points = {}
        driver_info = {}
        
        # Process each session result
        for result in session_results:
            driver_num = result['driver_number']
            position = result.get('position', 0)
            
            # Get driver info from another API call if needed
            if driver_num not in driver_info:
                try:
                    driver_url = f"https://api.openf1.org/v1/drivers?driver_number={driver_num}&session_key={result['session_key']}"
                    driver_response = requests.get(driver_url, timeout=5)
                    if driver_response.status_code == 200:
                        drivers_data = driver_response.json()
                        if drivers_data:
                            driver_info[driver_num] = drivers_data[0]
                except:
                    continue
            
            # Award points
            if position in points_system and not result.get('dnf', False):
                points = points_system[position]
                
                # Driver points
                if driver_num not in driver_points:
                    driver_points[driver_num] = 0
                driver_points[driver_num] += points
                
                # Constructor points
                if driver_num in driver_info:
                    team = driver_info[driver_num].get('team_name', 'Unknown')
                    if team not in constructor_points:
                        constructor_points[team] = 0
                    constructor_points[team] += points
        
        # Create driver standings
        driver_standings = []
        for driver_num, points in sorted(driver_points.items(), key=lambda x: x[1], reverse=True):
            if driver_num in driver_info:
                driver_standings.append({
                    'position': len(driver_standings) + 1,
                    'driver_code': driver_info[driver_num].get('name_acronym', 'UNK'),
                    'points': points,
                    'full_name': driver_info[driver_num].get('full_name', 'Unknown')
                })
        
        # Create constructor standings
        constructor_standings = []
        for team, points in sorted(constructor_points.items(), key=lambda x: x[1], reverse=True):
            constructor_standings.append({
                'position': len(constructor_standings) + 1,
                'team_name': team,
                'points': points
            })
        
        return driver_standings[:10], constructor_standings[:10]

    def fetch_track_coordinates(self, circuit_name: str) -> List[Tuple[float, float]]:
        """Fetch track coordinates from GitHub repository"""
        try:
            # Map circuit names to repository file names
            circuit_mapping = {
                'Monaco': 'monaco',
                'Silverstone': 'silverstone',
                'Monza': 'monza',
                'Spa-Francorchamps': 'spa',
                'Suzuka': 'suzuka',
                'Interlagos': 'interlagos',
                'Circuit de Barcelona-Catalunya': 'barcelona',
                'Hungaroring': 'hungaroring',
                'Singapore': 'singapore',
                'Baku': 'baku',
                'Jeddah': 'jeddah',
                'Imola': 'imola',
                'Miami': 'miami',
                'Austin': 'austin',
                'Mexico': 'mexico',
                'Las Vegas': 'vegas',
                'Abu Dhabi': 'abu_dhabi'
            }
            
            # Try to find matching circuit
            circuit_key = None
            for key, value in circuit_mapping.items():
                if key.lower() in circuit_name.lower() or value.lower() in circuit_name.lower():
                    circuit_key = value
                    break
            
            if not circuit_key:
                print(f"Circuit mapping not found for: {circuit_name}")
                return self.get_generic_track_coordinates()
            
            # Fetch from TUMFTM racetrack database (has coordinates)
            url = f"https://raw.githubusercontent.com/TUMFTM/racetrack-database/master/tracks/{circuit_key}/{circuit_key}_centerline.csv"
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                coordinates = []
                
                # Skip header if present
                start_idx = 1 if 'x' in lines[0].lower() or '#' in lines[0] else 0
                
                for line in lines[start_idx:]:
                    try:
                        if ',' in line:
                            parts = line.split(',')
                            x, y = float(parts[0]), float(parts[1])
                            coordinates.append((x, y))
                    except (ValueError, IndexError):
                        continue
                
                if coordinates:
                    print(f"Loaded {len(coordinates)} track coordinates for {circuit_name}")
                    return coordinates
            
            # Fallback to generic track if specific one not found
            print(f"Could not load specific track data for {circuit_name}, using generic track")
            return self.get_generic_track_coordinates()
            
        except Exception as e:
            print(f"Error fetching track coordinates: {e}")
            return self.get_generic_track_coordinates()

    def get_generic_track_coordinates(self) -> List[Tuple[float, float]]:
        """Generate a generic racing circuit outline"""
        coordinates = []
        # Create a stylized racing circuit with chicanes and turns
        
        # Main straight
        for i in range(0, 100, 2):
            coordinates.append((i, 0))
        
        # Turn 1 (right turn)
        for angle in range(0, 90, 5):
            x = 100 + 30 * math.cos(math.radians(angle))
            y = 30 * math.sin(math.radians(angle))
            coordinates.append((x, y))
        
        # Short straight
        for i in range(0, 40, 2):
            coordinates.append((130, 30 + i))
        
        # Chicane
        coordinates.extend([
            (125, 70), (120, 75), (115, 70), (110, 75), (105, 70)
        ])
        
        # Back straight
        for i in range(105, 20, -2):
            coordinates.append((i, 75))
        
        # Final turns back to start
        for angle in range(90, 270, 5):
            x = 20 + 20 * math.cos(math.radians(angle))
            y = 55 + 20 * math.sin(math.radians(angle))
            coordinates.append((x, y))
        
        # Connect back to start
        for i in range(20, 0, -1):
            coordinates.append((i, 35))
        
        return coordinates

    def fetch_openf1_data(self) -> bool:
        """Fetch data from OpenF1 API"""
        try:
            print("Fetching F1 data from OpenF1 API...")
            
            # Get current season
            current_year = datetime.now().year
            
            # Get latest session info for standings
            session_key, meeting_key = self.get_current_season_data()
            
            if not session_key:
                print("Could not get current session data, using fallback data")
                return self.use_fallback_data()
            
            # Get all race sessions from this year to calculate standings
            all_races_url = f"https://api.openf1.org/v1/sessions?year={current_year}&session_name=Race"
            races_response = requests.get(all_races_url, timeout=10)
            
            if races_response.status_code == 200:
                races = races_response.json()
                all_results = []
                
                # Get results from all completed races
                for race in races[:5]:  # Limit to avoid timeout, take recent 5 races
                    results_url = f"https://api.openf1.org/v1/session_result?session_key={race['session_key']}"
                    results_response = requests.get(results_url, timeout=5)
                    
                    if results_response.status_code == 200:
                        race_results = results_response.json()
                        all_results.extend(race_results)
                
                # Calculate championship standings
                if all_results:
                    self.drivers_data, self.constructors_data = self.calculate_championship_standings(all_results)
                else:
                    return self.use_fallback_data()
            
            # Get next race information
            meetings_url = f"https://api.openf1.org/v1/meetings?year={current_year}"
            meetings_response = requests.get(meetings_url, timeout=10)
            
            if meetings_response.status_code == 200:
                meetings = meetings_response.json()
                now = datetime.now(timezone.utc)
                
                # Find next upcoming race
                future_meetings = [m for m in meetings if datetime.fromisoformat(m['date_start'].replace('Z', '+00:00')) > now]
                
                if future_meetings:
                    next_meeting = min(future_meetings, key=lambda x: x['date_start'])
                    
                    self.next_race_data = {
                        'race_name': next_meeting['meeting_name'],
                        'location': next_meeting['location'],
                        'date': next_meeting['date_start'][:10],  # Extract date part
                        'track_name': next_meeting['circuit_short_name']
                    }
                    
                    # Fetch track coordinates
                    self.track_coordinates = self.fetch_track_coordinates(next_meeting['circuit_short_name'])
            
            self.last_update = time.time()
            print("OpenF1 data updated successfully")
            return True
            
        except Exception as e:
            print(f"Error fetching OpenF1 data: {e}")
            return self.use_fallback_data()

    def use_fallback_data(self) -> bool:
        """Use fallback data when API is unavailable"""
        print("Using fallback data...")
        
        # Current season fallback data (2024 season example)
        self.drivers_data = [
            {"position": 1, "driver_code": "VER", "points": 575, "full_name": "Max Verstappen"},
            {"position": 2, "driver_code": "PER", "points": 285, "full_name": "Sergio Perez"},
            {"position": 3, "driver_code": "HAM", "points": 234, "full_name": "Lewis Hamilton"},
            {"position": 4, "driver_code": "RUS", "points": 206, "full_name": "George Russell"},
            {"position": 5, "driver_code": "LEC", "points": 175, "full_name": "Charles Leclerc"}
        ]
        
        self.constructors_data = [
            {"position": 1, "team_name": "Red Bull Racing", "points": 860},
            {"position": 2, "team_name": "Mercedes", "points": 409},
            {"position": 3, "team_name": "Ferrari", "points": 280},
            {"position": 4, "team_name": "McLaren", "points": 267},
            {"position": 5, "team_name": "Aston Martin", "points": 159}
        ]
        
        # Next race fallback
        next_date = datetime.now()
        next_date = next_date.replace(day=min(28, next_date.day + 14))  # ~2 weeks from now
        
        self.next_race_data = {
            "race_name": "Next Grand Prix",
            "location": "TBD",
            "date": next_date.strftime("%Y-%m-%d"),
            "track_name": "Generic Circuit"
        }
        
        # Generic track coordinates
        self.track_coordinates = self.get_generic_track_coordinates()
        
        self.last_update = time.time()
        return True

    def draw_f1_logo(self, draw: ImageDraw, x: int, y: int, size: int = 20):
        """Draw a simple pixel-art F1 logo"""
        logo_width = size
        logo_height = size // 2
        
        # Draw "F1" in a bold, blocky style
        # F
        draw.rectangle([x, y, x + size//3, y + logo_height], fill=0)
        draw.rectangle([x, y, x + size//2, y + logo_height//4], fill=0)
        draw.rectangle([x, y + logo_height//3, x + size//3, y + logo_height//2], fill=0)
        
        # 1
        one_x = x + size//2 + 2
        draw.rectangle([one_x, y, one_x + size//6, y + logo_height], fill=0)
        draw.rectangle([one_x - size//12, y + logo_height - logo_height//8, 
                      one_x + size//4, y + logo_height], fill=0)

    def draw_podium(self, draw: ImageDraw, x: int, y: int, drivers: List[Dict]):
        """Draw podium with top 3 drivers"""
        if len(drivers) < 3:
            return
            
        # Podium positions (2nd, 1st, 3rd from left to right)
        positions = [
            (x, y + 8, drivers[1]),  # 2nd place (left, shorter)
            (x + 20, y, drivers[0]),  # 1st place (center, tallest)
            (x + 40, y + 12, drivers[2])  # 3rd place (right, shortest)
        ]
        
        heights = [17, 25, 13]  # Different heights for podium steps
        
        for i, (px, py, driver) in enumerate(positions):
            # Draw podium step
            draw.rectangle([px, py + (25 - heights[i]), px + 18, py + 25], fill=0)
            
            # Draw position number on step
            pos_text = str(driver["position"])
            bbox = draw.textbbox((0, 0), pos_text, font=self.font_small)
            text_width = bbox[2] - bbox[0]
            text_x = px + (18 - text_width) // 2
            draw.text((text_x, py + 25 - heights[i] + 2), pos_text, font=self.font_small, fill=255)
            
            # Draw driver code above podium
            driver_code = driver["driver_code"]
            bbox = draw.textbbox((0, 0), driver_code, font=self.font_small)
            text_width = bbox[2] - bbox[0]
            text_x = px + (18 - text_width) // 2
            draw.text((text_x, py - 12), driver_code, font=self.font_small, fill=0)

    def draw_track_outline_from_coordinates(self, draw: ImageDraw, coordinates: List[Tuple[float, float]], 
                                         x: int, y: int, width: int, height: int):
        """Draw track outline from coordinate data as pixel art"""
        if not coordinates:
            self.draw_generic_track(draw, x, y, width, height)
            return
        
        # Find bounding box of coordinates
        min_x = min(coord[0] for coord in coordinates)
        max_x = max(coord[0] for coord in coordinates)
        min_y = min(coord[1] for coord in coordinates)
        max_y = max(coord[1] for coord in coordinates)
        
        # Calculate scale to fit in display area
        coord_width = max_x - min_x
        coord_height = max_y - min_y
        
        if coord_width == 0 or coord_height == 0:
            self.draw_generic_track(draw, x, y, width, height)
            return
        
        scale_x = (width - 10) / coord_width
        scale_y = (height - 10) / coord_height
        scale = min(scale_x, scale_y)  # Use uniform scaling
        
        # Center the track in the available space
        scaled_width = coord_width * scale
        scaled_height = coord_height * scale
        offset_x = x + (width - scaled_width) // 2
        offset_y = y + (height - scaled_height) // 2
        
        # Convert coordinates to screen space and create pixel art effect
        screen_coords = []
        for coord_x, coord_y in coordinates:
            screen_x = int(offset_x + (coord_x - min_x) * scale)
            screen_y = int(offset_y + (coord_y - min_y) * scale)
            screen_coords.append((screen_x, screen_y))
        
        # Draw the track with thick lines for pixel art effect
        for i in range(len(screen_coords) - 1):
            x1, y1 = screen_coords[i]
            x2, y2 = screen_coords[i + 1]
            
            # Draw thick line (3 pixels wide for visibility on small display)
            draw.line([x1, y1, x2, y2], fill=0, width=3)
            
            # Add small circles at key points for pixel art effect
            if i % 3 == 0:  # Every 3rd point
                draw.ellipse([x1-1, y1-1, x1+1, y1+1], fill=0)
        
        # Connect last point to first to close the circuit
        if screen_coords:
            x1, y1 = screen_coords[-1]
            x2, y2 = screen_coords[0]
            draw.line([x1, y1, x2, y2], fill=0, width=3)
        
        # Add start/finish line indicator
        if screen_coords:
            start_x, start_y = screen_coords[0]
            # Draw start/finish line perpendicular to track direction
            draw.line([start_x-3, start_y-3, start_x+3, start_y+3], fill=0, width=2)
            draw.line([start_x-3, start_y+3, start_x+3, start_y-3], fill=0, width=2)

    def draw_generic_track(self, draw: ImageDraw, x: int, y: int, width: int, height: int):
        """Draw a generic racing circuit when specific track data isn't available"""
        center_x = x + width // 2
        center_y = y + height // 2
        
        # Simple oval track with some characteristic turns
        oval_width = width - 20
        oval_height = height - 20
        
        # Main oval
        draw.ellipse([center_x - oval_width//2, center_y - oval_height//2,
                     center_x + oval_width//2, center_y + oval_height//2], 
                    outline=0, width=3)
        
        # Add some turns for character
        # Chicane
        chicane_x = center_x + oval_width//4
        chicane_y = center_y
        draw.polygon([
            (chicane_x-5, chicane_y-8),
            (chicane_x+2, chicane_y-5),
            (chicane_x-2, chicane_y+5),
            (chicane_x+5, chicane_y+8)
        ], outline=0, width=2)
        
        # Start/finish line
        draw.line([center_x - 2, center_y - oval_height//2, 
                  center_x + 2, center_y - oval_height//2], fill=0, width=3)

    def create_leaderboard_screen(self) -> Image:
        """Create the main leaderboard screen"""
        img = Image.new('1', (self.width, self.height), 255)  # White background
        draw = ImageDraw.Draw(img)
        
        # Top center: Current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        bbox = draw.textbbox((0, 0), current_date, font=self.font_small)
        date_width = bbox[2] - bbox[0]
        draw.text(((self.width - date_width) // 2, 2), current_date, font=self.font_small, fill=0)
        
        # Top left: Next race info
        if self.next_race_data:
            next_race_text = f"{self.next_race_data['date']} {self.next_race_data['location']}"
            draw.text((2, 2), next_race_text, font=self.font_small, fill=0)
        
        # Center: F1 logo
        self.draw_f1_logo(draw, self.width // 2 - 15, 20)
        
        # Right side: Top 5 drivers
        driver_start_x = self.width - 80
        driver_start_y = 15
        
        draw.text((driver_start_x, driver_start_y - 12), "DRIVERS", font=self.font_small, fill=0)
        
        for i, driver in enumerate(self.drivers_data[:5]):
            y_pos = driver_start_y + (i * 12)
            driver_text = f"{driver['position']}. {driver['driver_code']} {driver['points']}"
            draw.text((driver_start_x, y_pos), driver_text, font=self.font_small, fill=0)
        
        # Bottom left: Top 5 constructors
        team_start_x = 2
        team_start_y = self.height - 60
        
        draw.text((team_start_x, team_start_y - 12), "CONSTRUCTORS", font=self.font_small, fill=0)
        
        for i, team in enumerate(self.constructors_data[:5]):
            y_pos = team_start_y + (i * 10)
            team_name = self.team_abbreviations.get(team['team_name'], team['team_name'][:10])
            team_text = f"{team['position']}. {team_name}"
            draw.text((team_start_x, y_pos), team_text, font=self.font_small, fill=0)
        
        # Bottom center: Podium
        if len(self.drivers_data) >= 3:
            podium_x = self.width // 2 - 30
            podium_y = self.height - 40
            self.draw_podium(draw, podium_x, podium_y, self.drivers_data[:3])
        
        return img

    def create_track_screen(self) -> Image:
        """Create the next race track screen"""
        img = Image.new('1', (self.width, self.height), 255)  # White background
        draw = ImageDraw.Draw(img)
        
        if not self.next_race_data:
            draw.text((10, 50), "No race data available", font=self.font_medium, fill=0)
            return img
        
        # Top center: Track name and location
        track_text = f"{self.next_race_data['race_name']}"
        bbox = draw.textbbox((0, 0), track_text, font=self.font_large)
        track_width = bbox[2] - bbox[0]
        draw.text(((self.width - track_width) // 2, 5), track_text, font=self.font_large, fill=0)
        
        location_text = self.next_race_data['location']
        bbox = draw.textbbox((0, 0), location_text, font=self.font_medium)
        location_width = bbox[2] - bbox[0]
        draw.text(((self.width - location_width) // 2, 20), location_text, font=self.font_medium, fill=0)
        
        # Center: Track outline (pixel art style)
        track_area_x = 20
        track_area_y = 35
        track_area_width = self.width - 40
        track_area_height = 60
        
        self.draw_track_outline_from_coordinates(draw, self.track_coordinates,
                                               track_area_x, track_area_y, 
                                               track_area_width, track_area_height)
        
        # Bottom: Race date
        date_text = f"Race Date: {self.next_race_data['date']}"
        bbox = draw.textbbox((0, 0), date_text, font=self.font_medium)
        date_width = bbox[2] - bbox[0]
        draw.text(((self.width - date_width) // 2, self.height - 15), date_text, font=self.font_medium, fill=0)
        
        return img

    def update_display(self, image: Image):
        """Update the e-paper display with new image"""
        if HAS_EPAPER:
            # Convert PIL image to format expected by Waveshare library
            self.epd.display(self.epd.getbuffer(image))
        else:
            # Save image for testing without actual hardware
            filename = f"f1_display_screen_{self.current_screen}_{int(time.time())}.png"
            image.save(filename)
            print(f"Display updated (saved as {filename})")

    def run(self):
        """Main execution loop"""
        print("Starting F1 Leaderboard Display...")
        print("Fetching data from OpenF1 API...")
        
        # Initial data fetch
        if not self.fetch_openf1_data():
            print("Failed to fetch initial data, using fallback data")
        
        try:
            while True:
                # Update data every 5 minutes
                if time.time() - self.last_update > 300:
                    print("Updating data...")
                    self.fetch_openf1_data()
                
                # Create and display current screen
                if self.current_screen == 0:
                    print("Displaying leaderboard screen...")
                    image = self.create_leaderboard_screen()
                else:
                    print("Displaying track screen...")
                    image = self.create_track_screen()
                
                self.update_display(image)
                
                # Switch screens every 30 seconds
                time.sleep(30)
                self.current_screen = 1 - self.current_screen  # Toggle between 0 and 1
                
        except KeyboardInterrupt:
                    print("\nShutting down F1 Display...")
                    if HAS_EPAPER:
                        self.epd.init()
                        self.epd.Clear(0xFF)
                        self.epd.sleep()
        except Exception as e:
            print(f"Unexpected error: {e}")
            if HAS_EPAPER:
                self.epd.init()
                self.epd.Clear(0xFF)
                self.epd.sleep()

def main():
    """Main entry point"""
    print("="*50)
    print("F1 Leaderboard Display Starting...")
    print("Waveshare 2.13\" e-Paper Edition")
    print("Live data from OpenF1 API")
    print("="*50)
    
    try:
        display = F1LeaderboardDisplay()
        display.run()
    except Exception as e:
        print(f"Failed to start F1 Display: {e}")
        print("Check your hardware connections and try again.")

if __name__ == "__main__":
    main()

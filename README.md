# **Smart Climate Control for Home Assistant**

This project started out as a Node-RED flow but has been rebuilt as a native Home Assistant integration.

The goal is to make climate management simpler and more flexible instead of editing flows,

configuration can now be adjusted directly from the Home Assistant control panel.

The majority of the code was generated with the help of AI, with my role focused on integration, testing, and making it work within my setup.

## **🌟 Features**

* **🌡️ Intelligent Temperature Control**  
  * **Heating & Cooling Modes**: Full-featured heating and smart cooling support  
  * Deadband control to prevent rapid cycling  
  * Weather compensation for cold days (heating mode only)  
  * Multiple temperature presets for heating (Comfort, Eco, Boost) and cooling (Comfort, Eco)  
  * Adjustable temperature settings via frontend number entities  
* **☀️ Solar Synchronization (Battery Saver)**  
  * Acts as a thermal battery: uses excess solar power (W) to safely overheat/overcool the house by a configurable offset.  
  * Automatically shifts back to normal target temperatures when solar production drops.  
* **💨 Advanced HRV Ventilation Control**  
  * **Auto Free Cooling**: Automatically pulls in cool outside air when the house is too warm, bypassing the heat pump to save energy.  
  * **Airout Mode**: Manual or automatic single-direction ventilation for rapid air exchange.  
  * **Smart Humidity Lock**: Fixes fan direction to quickly extract moisture if only one room is highly humid.  
  * **Frost Protection**: Disables humidity direction-lock if the outside temperature drops below 15°C to preserve heat recovery efficiency.  
* **🏠 Smart Home Integration**  
  * Occupancy-based heating/cooling via presence tracker (Auto-Eco when away)  
  * Sleep detection for automatic eco mode (heating only, requires bed sensor)  
  * Door/window monitoring to prevent energy waste (pauses HVAC after delay)  
* **Heat Pump Contact Sensor**: Binary sensor to verify heat pump is actually running (recommended for IR/SmartIR controlled devices)

## **🔥❄️ Heating vs Cooling Modes**

### **Heating Mode (HEAT/AUTO)**

Full-featured intelligent heating with:

* Multiple temperature presets (Comfort, Eco, Boost)  
* Sleep detection (automatic eco mode)  
* Weather compensation for cold days  
* House average temperature safety limits  
* Solar Sync thermal storage

### **Cooling Mode (COOL)**

Intelligent cooling with:

* Two presets: Comfort (when home) and Eco (when away)  
* Inverted deadband control (cool when hot, stop when cool)  
* Auto Free Cooling integration (uses outside air instead of the compressor when possible)  
* Solar Sync thermal storage

## **📋 Prerequisites**

* Home Assistant 2024.1.0 or newer  
* HACS (Home Assistant Community Store) installed  
* The following entities in your Home Assistant:  
  * A climate entity (heat pump/thermostat) that supports both heating and cooling  
  * Room temperature sensor  
  * Outside temperature sensor (optional but recommended for weather compensation, free cooling, and frost protection)

## **🚀 Installation**

### **Via HACS (Recommended)**

1. Open HACS in your Home Assistant instance  
2. Click on "Integrations"  
3. Click the three dots menu in the top right  
4. Select "Custom repositories"  
5. Add this repository URL: https://github.com/smartthings54/smart-climate-control  
6. Select "Integration" as the category  
7. Click "Add"  
8. Search for "Smart Climate Control"  
9. Click "Download"  
10. Restart Home Assistant

### **Manual Installation**

1. Download the latest release from GitHub  
2. Extract the smart\_climate\_control folder  
3. Copy it to your custom\_components directory:  
   config/custom\_components/smart\_climate\_control/

4. Restart Home Assistant

## **⚙️ Configuration**

### **Initial Setup**

1. Go to **Settings** → **Devices & Services**  
2. Click **\+ Add Integration**  
3. Search for **Smart Climate Control**  
4. Follow the setup wizard to select your entities.

### **Configuration Options**

#### **Required Entities**

* **Heat Pump Entity**: Your climate device to control  
* **Room Temperature Sensor**: The main room temperature

#### **Optional Entities**

* **Outside Temperature Sensor**: For weather comp, free cooling, and winter HRV frost protection.  
* **Average House Temperature**: For whole-house safety limits (heating).  
* **Window/Door Sensors**: Disable HVAC when open for \> configured delay.  
* **Presence Tracker**: For occupancy-based control (Auto-Eco).  
* **Bed Sensor**: For sleep detection (heating mode).  
* **Solar Sensor (Power)**: Power sensor (W) tracking your solar excess/production.  
* **Ventilation Fans & Humidity Sensors**: For HRV and Free Cooling controls.

#### **Adjustable Settings (via HA UI Number Entities)**

* **Heating Comfort**: Default 20.0°C  
* **Heating Eco**: Default 18.0°C  
* **Heating Boost**: Default 23.0°C  
* **Cooling Comfort**: Default 24.0°C  
* **Cooling Eco**: Default 27.0°C  
* **Solar Threshold (W)** & **Solar Offset (°C)**  
* **Ventilation Cycle, Duration, Fan Speed, Airout Duration**  
* **Free Cooling Max Duration & Cooldown**  
* **Humidity Threshold**

## **🎛️ Created Entities**

### **Climate Entity**

* **climate.YOUR\_CLIMATE\_ENTITY** \- Main climate control with OFF/HEAT/COOL/AUTO modes

### **Switches**

* **switch.smart\_climate\_climate\_management** \- Master enable/disable for smart control  
* **switch.smart\_climate\_force\_comfort\_mode** \- Force comfort temperature  
* **switch.smart\_climate\_force\_eco\_mode** \- Force eco temperature  
* **switch.smart\_climate\_force\_cooling\_mode** \- Force cooling mode  
* **switch.smart\_climate\_ventilation\_enabled** \- Enable auto ventilation (HRV)  
* **switch.smart\_climate\_airout** \- Trigger single-direction manual Airout  
* **switch.smart\_climate\_auto\_free\_cooling** \- Enable/Disable Auto Free Cooling  
* **switch.smart\_climate\_solar\_sync** \- Enable/Disable Solar Battery Saver

### **Select**

* **select.smart\_climate\_airout\_direction** \- Choose Airout direction (forward/reverse)

### **Sensors**

* **sensor.smart\_climate\_status** \- Current system status and debug info  
* **sensor.smart\_climate\_mode** \- Current active mode  
* **sensor.smart\_climate\_target** \- Target temperature being used  
* **sensor.smart\_climate\_ventilation\_status** \- Details on fan phases and timers

### **Number Entities**

Various sliders to adjust temperatures (Boost, Comfort, Eco, Cooling, Cooling Eco), Deadbands, Solar thresholds, and Ventilation settings on the fly.

## **📱 Dashboard Cards**

### **Basic Status & Control Card**

type: vertical-stack  
cards:  
  \- type: thermostat  
    entity: climate.YOUR\_CLIMATE\_ENTITY  
  \- type: entities  
    entities:  
      \- entity: sensor.smart\_climate\_status  
      \- entity: sensor.smart\_climate\_mode  
      \- entity: switch.smart\_climate\_climate\_management  
      \- entity: switch.smart\_climate\_solar\_sync  
      \- entity: switch.smart\_climate\_auto\_free\_cooling

### **Advanced Settings Card**

type: entities  
title: Smart Climate Settings  
entities:  
  \- entity: number.smart\_climate\_comfort\_temperature  
  \- entity: number.smart\_climate\_eco\_temperature  
  \- entity: number.smart\_climate\_cooling\_temperature  
  \- entity: number.smart\_climate\_cooling\_eco\_temperature  
  \- entity: number.smart\_climate\_solar\_threshold  
  \- entity: number.smart\_climate\_solar\_offset

### **Ventilation & Airout Card**

type: entities  
title: Ventilation Control  
entities:  
  \- entity: sensor.smart\_climate\_ventilation\_status  
  \- entity: switch.smart\_climate\_airout  
  \- entity: select.smart\_climate\_airout\_direction  
  \- entity: number.smart\_climate\_airout\_max\_duration

## **🎯 How It Works**

The system operates on a 60-second cycle for HVAC and a 2-second cycle for precise HRV fan syncing:

1. **Presence & Solar Check**: Evaluates if someone is home (Comfort vs Eco) and if solar excess meets the threshold (applies offset).  
2. **Free Cooling Check**: If it's hot inside but cool outside, bypasses the AC and triggers the Airout fans instead.  
3. **Humidity Check**: Normal HRV alternates fan directions. If one room is highly humid and outside is \> 15°C, it locks the direction to extract moisture fast.  
4. **Deadband Logic**:  
   * **Heating**: Turn ON when Room ≤ (Target \- Deadband Below). Turn OFF when Room ≥ (Target \+ Deadband Above).  
   * **Cooling**: Turn ON when Room ≥ (Target \+ Deadband Above). Turn OFF when Room ≤ (Target \- Deadband Below).

## **🐛 Troubleshooting**

### **System Not Heating/Cooling**

1. Check if **Climate Management** switch is ON.  
2. Check if a window/door sensor is triggered (pauses HVAC).  
3. Review the **Status** sensor for details (it might be in a deadband holding pattern).  
4. Verify Solar Sync isn't throwing the target temperature too high/low.

### **Ventilation Stuck in One Direction**

1. Check if an **Airout** or **Free Cooling** cycle is currently active.  
2. Check if the **Humidity Threshold** is exceeded in only one room (and outside is \> 15°C).

## **📝 Support**

* **Issues**: [GitHub Issues](https://github.com/smartthings54/smart-climate-control/issues)  
* **Discussions**: [GitHub Discussions](https://github.com/smartthings54/smart-climate-control/discussions)

## **📄 License**

This project is licensed under the MIT License \- see the [LICENSE](http://docs.google.com/LICENSE) file for details.
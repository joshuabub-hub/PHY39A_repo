```bash
cd "/Users/joshbub/Documents/PHYS39A_Repo/PHY39A_repo/Module 6" && venv/bin/python Python/serial_plot_mod6.py
```

T_63 = 35.7

tau = 49.8

For the simulated run we had chih=0.515, chic=0.135, tau=200s, Tamb=22, u=100, delt=0.1s

Differences between model and apparatus: As close as we can get to simulating the environmental effects, we likely will not perfectally simulate them as the thermistor is not perfectly coupled with the TEC, so we are not 100% sure of the exact temperature. 

**Heating**

| Run | Controller | Choice | Temp Set Point | Starting Temp | Observation |
|-----|------------|--------|----------------|---------------|-------------|
| 1   |  P         |    5   |           30ºC |          22ºC | Large droop ~2ºC |
| 2   | P          | 50     | 30ºC | 22ºC | overshot then settled to set point after short overdamped oscillation |
| 3   | P          | 500    | 30ºC | 22ºC | |
| 4   | PI         | Intermediate Kp, low Ki | 30ºC | 22ºC | |
| 5   | PI         | High Kp, intermediate Ki | 30ºC | 22ºC | |
| 6   | PI         | High Kp, high Ki | 30ºC | 22ºC | |

**Cooling**

| Run | Controller | Choice | Temp Set Point | Starting Temp | Observation |
|-----|------------|--------|----------------|---------------|-------------|
| 1 | P | 5 | 15ºC | 22ºC | |
| 2 | P | 50 | 15ºC | 22ºC | |
| 3 | P | 500 | 15ºC | 22ºC | |
| 4 | PI | Intermediate Kp, low Ki | 15ºC | 22ºC | |
| 5 | PI | High Kp, intermediate Ki | 15ºC | 22ºC | |
| 6 | PI | High Kp, high Ki | 15ºC | 22ºC | |

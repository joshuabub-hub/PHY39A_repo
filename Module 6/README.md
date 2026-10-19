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
| 1   |  P         |    Kp = 5   |           30ºC |          22ºC | Large droop ~2ºC |
| 2   | P          | Kp = 50     | 30ºC | 22ºC | overshot then settled to set point after short overdamped oscillation, small error ~0.3ºC |
| 3   | P          | Kp = 500    | 30ºC | 22ºC | overshot then settled into small oscillations, PWM cooling periodically saturates|
| 4   | PI         | Kp = 40, Ki = 0.1 | 30ºC | 22ºC | overshot into overdamped oscillation, settled with small steady state error ~0.30ºC which was decreasing slowly|
| 5   | PI         | Kp = 40, Ki = 0.5| 30ºC | 22ºC | overshot into overdamped oscillation, PWM briefly saturated, settled with small steady state error ~0.15ºC, which was decreasing slowly |
| 6   | PI         | Kp = 40, Ki = 10 | 30ºC | 22ºC | overshot (more than previous run) into overdamped oscillation (more periods than previous run), PWM initially saturates, settled with ~0 error |

**Cooling**

| Run | Controller | Choice | Temp Set Point | Starting Temp | Observation |
|-----|------------|--------|----------------|---------------|-------------|
| 1 | P | 5 | 15ºC | 22ºC | No overshoot, slowly approached 15ºC with large steady state error ~ 5ºC|
| 2 | P | 50 | 15ºC | 22ºC | No overshoot, quickly dropped to 16ºC and slowly progressed below with some droop|
| 3 | P | 500 | 15ºC | 22ºC | briefly overshot into small oscilations, PWM initially saturates|
| 4 | PI |  Kp = 40, Ki = 0.1| 15ºC | 22ºC | Exp decay to ~16ºC, slow decrease after that|
| 5 | PI | Kp = 40, Ki = 0.5| 15ºC | 22ºC | exp decay to ~15ºC, steady state error ~0.2ºC, no overshoot from PI control trials yet|
| 6 | PI | Kp = 40, Ki = 10 | 15ºC | 22ºC | Overshot slightly, PWM saturated briefly, settled without oscillations w/ steady state error ~0.01ºC |

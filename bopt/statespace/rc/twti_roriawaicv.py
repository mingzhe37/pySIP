from dataclasses import dataclass

from ..base import RCModel


@dataclass
class TwTi_RoRiAwAicv(RCModel):
    """Second order RC model"""

    states = [
        ('TEMPERATURE', 'xw', 'wall temperature'),
        ('TEMPERATURE', 'xi', 'indoor space temperature')
    ]

    params = [
        ('THERMAL_RESISTANCE', 'Ro', 'between the outdoor and the wall node'),
        ('THERMAL_RESISTANCE', 'Ri', 'between the wall node and the indoor'),
        ('THERMAL_CAPACITY', 'Cw', 'Wall'),
        ('THERMAL_CAPACITY', 'Ci', 'indoor air, indoor walls, furnitures, etc. '),
        ('SOLAR_APERTURE', 'Aw', 'of the wall (m2)'),
        ('SOLAR_APERTURE', 'Ai', 'of the windows (m2)'),
        ('COEFFICIENT', 'cv', 'scaling of the heating contribution of the ventilation'),
        ('STATE_DEVIATION', 'sigw_w', ''),
        ('STATE_DEVIATION', 'sigw_i', ''),
        ('MEASURE_DEVIATION', 'sigv', ''),
        ('INITIAL_MEAN', 'x0_w', ''),
        ('INITIAL_MEAN', 'x0_i', ''),
        ('INITIAL_DEVIATION', 'sigx0_w', ''),
        ('INITIAL_DEVIATION', 'sigx0_i', '')
    ]

    inputs = [
        ('TEMPERATURE', 'To', 'outdoor air temperature'),
        ('POWER', 'Qgh', 'global horizontal solar radiation'),
        ('POWER', 'Qh', 'HVAC system heat'),
        ('POWER', 'Qv', 'heat from the ventilation system')
    ]

    outputs = [
        ('TEMPERATURE', 'xi', 'indoor air temperature')
    ]

    def set_constant(self):
        self.C[0, 1] = 1.0

    def set_jacobian(self):
        self.dQ['sigw_w'][0, 0] = 1.0
        self.dQ['sigw_i'][1, 1] = 1.0
        self.dR['sigv'][0, 0] = 1.0
        self.dx0['x0_w'][0, 0] = self.sX
        self.dx0['x0_i'][1, 0] = self.sX
        self.dP0['sigx0_w'][0, 0] = 1.0
        self.dP0['sigx0_i'][1, 1] = 1.0

    def update_state_space_model(self):
        (Ro, Ri, Cw, Ci, Aw, Ai, cv, sigw_w, sigw_i, sigv, x0_w, x0_i, sigx0_w, sigx0_i, *_) = self.parameters.theta

        self.A[:] = [
            [-(Ro + Ri) / (Cw * Ri * Ro * self.sC), 1. / (Cw * Ri * self.sC)],
            [1. / (Ci * Ri * self.sC), -1. / (Ci * Ri * self.sC)]
        ]

        self.B[0, :2] = [1. / (Cw * Ro * self.sC), Aw / (Cw * self.sC)]
        self.B[1, 1:] = [Ai / (Ci * self.sC), 1. / (Ci * self.sC), cv / (Ci * self.sC)]

        self.Q[0, 0] = sigw_w
        self.Q[1, 1] = sigw_i

        self.R[0, 0] = sigv

        self.x0[0, 0] = x0_w * self.sX
        self.x0[1, 0] = x0_i * self.sX

        self.P0[0, 0] = sigx0_w
        self.P0[1, 1] = sigx0_i

    def update_jacobian(self):
        (Ro, Ri, Cw, Ci, Aw, Ai, cv, *_) = self.parameters.theta

        self.dA['Ro'][0, 0] = 1. / (Cw * Ro**2 * self.sC)

        self.dA['Ri'][:] = [
            [1. / (Cw * Ri**2 * self.sC), -1. / (Cw * Ri**2 * self.sC)],
            [-1. / (Ci * Ri**2 * self.sC), 1. / (Ci * Ri**2 * self.sC)]
        ]

        self.dA['Cw'][0, :] = [(Ro + Ri) / (Cw**2 * Ri * Ro * self.sC), -1. / (Cw**2 * Ri * self.sC)]

        self.dA['Ci'][1, :] = [-1. / (Ci**2 * Ri * self.sC), 1. / (Ci**2 * Ri * self.sC)]

        self.dB['Ro'][0, 0] = -1. / (Cw * Ro**2 * self.sC)

        self.dB['Cw'][0, :2] = [-1. / (Cw**2 * Ro * self.sC), -Aw / (Cw**2 * self.sC)]

        self.dB['Ci'][1, 1:] = [-Ai / (Ci**2 * self.sC), -1. / (Ci**2 * self.sC), -cv / (Ci**2 * self.sC)]

        self.dB['Aw'][0, 1] = 1. / (Cw * self.sC)

        self.dB['Ai'][1, 1] = 1. / (Ci * self.sC)

        self.dB['cv'][1, 3] = 1. / (Ci * self.sC)
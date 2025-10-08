from numpy import log10

class RfUtils:
    """"""
    
    @staticmethod
    def refer_psd_to_isotropic(psd_dbm_hz: float, ant_gain_dbi: float) -> float:
        """"""
        return psd_dbm_hz - ant_gain_dbi


    @staticmethod
    def v2hz_to_dbm_hz(v2_hz, impedance_ohm):
        """"""
        return 10 * log10(v2_hz / impedance_ohm) + 30
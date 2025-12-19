import math

class Fluid:
    """流体物性"""
    def __init__(self, rho=900.0, mu=0.0288):
        self.rho = rho    # 密度 kg/m3
        self.mu = mu      # 动力粘度 Pa.s
        self.nu = mu/rho  # 运动粘度 m2/s

def calc_reynolds(v: float, D: float, nu: float) -> float:
    """计算雷诺数 Re = v*D/nu"""
    if v < 1e-6: return 0.0
    return abs(v * D / nu)

def calc_pipe_conductance(pipe, fluid: Fluid, dP: float) -> float:
    """计算管路流导 G (非线性核心)"""
    # 暂时返回一个固定的小常数，防止报错，后面完善
    return 1e-5
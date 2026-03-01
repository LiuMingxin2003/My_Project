
p = float(input("本金："))
R = float(input("年利率：")) / 100
years = int(input("还款年数："))

m = years * 12
monthly_rate = R / 12

numerator = p * monthly_rate * (1 + monthly_rate) ** m
denominator = (1 + monthly_rate) ** m - 1
Result = numerator / denominator

print(f"每月还：{Result:.2f} 元")
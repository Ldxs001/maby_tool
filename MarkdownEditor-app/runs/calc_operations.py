# run-name: calc_operations
def add(data):
    try:
        nums = [int(v) for k, v in data['kv'].items() if v.isdigit()]
        return f' {sum(nums)}'
    except Exception as e:
        return '加法 错误：非数字值'

def subtract(data):
    try:
        nums = [int(v) for k, v in data['kv'].items() if v.isdigit()]
        result = nums[0] - sum(nums[1:])
        return f' {result}'
    except Exception as e:
        return '减法 错误：非数字值'

def multiply(data):
    try:
        nums = [int(v) for k, v in data['kv'].items() if v.isdigit()]
        result = 1
        for num in nums:
            result *= num
        return f' {result}'
    except Exception as e:
        return '乘法 错误：非数字值'

def divide(data):
    try:
        nums = [int(v) for k, v in data['kv'].items() if v.isdigit()]
        if not nums or nums[0] == 0:
            return '除法 错误：除零或无数值'
        result = nums[0]
        for num in nums[1:]:
            if num == 0:
                return '除法 错误：包含除零'
            result /= num
        return f' {result:.2f}'
    except Exception as e:
        return '除法 错误：非数字值'

def run(data):
    add_result = add(data)
    sub_result = subtract(data)
    mul_result = multiply(data)
    div_result = divide(data)
    return f'{add_result}、{sub_result}、{mul_result}、{div_result}'
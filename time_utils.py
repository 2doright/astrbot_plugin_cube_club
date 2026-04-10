# 时间转换工具类
class TimeConvert:
    DNF_VALUE = 999999.0

    @staticmethod
    def time_to_seconds(time_str: str) -> float:
        """将 '1:23.456' 或 '83.456' 格式的字符串转为秒数（float）。支持 DNF。"""
        if time_str.upper() == "DNF":
            return TimeConvert.DNF_VALUE
            
        parts = time_str.split(':')
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = round(float(parts[1]), 3)
            if minutes < 0 or seconds < 0:
                raise ValueError("Invalid time format. Minutes and seconds cannot be negative.")
            return round(minutes * 60 + seconds, 3)
        return round(float(parts[0]), 3)

    @staticmethod
    def seconds_to_time(seconds) -> str:
        """将秒数（float）转为 '1:23.456' 或 '83.456' 格式字符串；None/'Null' 返回 'Null'。支持 DNF。"""
        if seconds is None or seconds == 'Null':
            return 'Null'
        if seconds >= TimeConvert.DNF_VALUE:
            return 'DNF'
            
        minutes = int(seconds // 60)
        remaining = round(seconds % 60, 3)
        
        # 格式化秒数：保留 2-3 位小数
        sec_str = f"{remaining:.2f}"
        if minutes == 0:
            return sec_str
        return f"{minutes}:{remaining:05.2f}" # 例如 1:05.20


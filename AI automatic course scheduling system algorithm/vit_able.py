import pandas as pd

# 假设 df 是您的 DataFrame
df = pd.DataFrame({
    'task_id': ['570102KBOB03', '590101B0A15', '460110B0B01', '570101KB0A07-1', '590101B0A27'],
    '课程编号': [130, 381, 481, 339, 611],
    '教师编号': ['教师A', '教师B', '教师C', '教师D', '教师E'],  # 假设教师编号映射为名称
    '课程列表': ["23学前教育5班", "23党务工作1班", "24智能焊接技术1班", "23早期教育1班", "23社会工作1班"],
    '教室': ['XDNYZX211', 'XDNYZX101', 'ZHL2-201', 'ZHL4-412', 'XDNYZX203'],
    'day_of_week': [1, 3, 4, 0, 1],  # 0=周一,1=周二,3=周四,4=周五
    'period': [4, 4, 4, 5, 6]
})

# 将数字星期转换为中文
df['day_of_week'] = df['day_of_week'].map({0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'})

# 使用 Styler 美化表格
styled_df = (df.style
    .set_table_styles([{'selector': 'th', 'props': [('background-color', '#f2f2f2')]}])
    .set_properties(**{'background-color': 'white', 'color': 'black'})
    .set_properties(subset=pd.IndexSlice[:, :], **{'display': 'none'})  # 隐藏索引列
    .bar(subset=['period'], color='#FFA07A')
)

styled_df
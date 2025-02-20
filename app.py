import pandas as pd
import streamlit as st
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
import logging
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    filename='app.log',
    format='%(asctime)s - %(message)s',
    level=logging.INFO
)

def log_action(action):
    user = st.session_state.get('user', 'unknown')
    logging.info(f"User: {user} - {action}")

# Конфигурация
DAYS_IN_MONTH = 28
NORM_HOURS = 160
WORK_GROUPS = ['ГР1', 'ГР2', 'ГР3', 'ГР4', 'офис']
STATUS_COLORS = {
    'отпуск': '#90EE90',
    'б/л': '#FFB6C1',
    'уч.отпуск': '#87CEEB',
    'переработка': '#FFFACD'
}

# Шаблоны графиков
SCHEDULE_TEMPLATES = {
    'График1': [11.5, 11.5, "", 11.5, 11.5, "", "", "", 11.5, 11.5],
    'График2': [11.5, 7.5, "", "", 11.5, 11.5, "", 11.5, 11.5],
    'График3': ["", 11.5, 11.5, "", "", "", 11.5, 11.5],
    'График4': ["", "", 11.5, 11.5, "", 11.5, 11.5],
    'Офис': [8, 8, 8, 8, 8]
}

class EmployeeSchedule:
    def __init__(self, name, group, schedule_type, exceptions=None, absences=None):
        self.name = name
        self.group = group
        self.schedule_type = schedule_type
        self.exceptions = exceptions or {}
        self.absences = absences or {}

    def generate_schedule(self):
        base_pattern = SCHEDULE_TEMPLATES[self.schedule_type]
        schedule = {}
        
        pattern_index = 0
        for day in range(1, DAYS_IN_MONTH+1):
            day_str = str(day)
            if day_str in self.exceptions:
                schedule[day_str] = self.exceptions[day_str]
            elif day_str in self.absences:
                schedule[day_str] = self.absences[day_str]
            else:
                schedule[day_str] = base_pattern[pattern_index % len(base_pattern)]
                pattern_index += 1
        
        total = sum(
            float(h) if isinstance(h, (int, float, str)) and str(h).replace('.', '').isdigit() 
            else 0 
            for h in schedule.values()
        )
        
        return {
            'Ф.И.О. мастера смены': self.name,
            'ГР №': self.group,
            **schedule,
            'Факт ФРВ': round(total, 1),
            'от ФРВ': round(total - NORM_HOURS, 1),
            'Статус': self.get_status()
        }

    def get_status(self):
        statuses = []
        for day in range(1, DAYS_IN_MONTH+1):
            val = self.absences.get(str(day), '')
            if val in STATUS_COLORS:
                statuses.append(val)
        return ', '.join(set(statuses)) if statuses else 'активен'

# Функции стилизации
def style_cells(row):
    styles = []
    for day in range(1, DAYS_IN_MONTH+1):
        val = row[str(day)]
        style = ''
        for status, color in STATUS_COLORS.items():
            if val == status or (isinstance(val, (int, float)) and val > NORM_HOURS and status == 'переработка'):
                style = f'background-color: {color}; color: #000;'
                break
        styles.append(style)
    return styles

# Шаблоны исключений
def absence_template():
    if 'schedule_data' not in st.session_state:
        st.warning("Данные не загружены!")
        return
    
    try:
        employees_list = st.session_state.schedule_data['Ф.И.О. мастера смены'].tolist()
    except KeyError as e:
        st.error(f"Ошибка структуры данных: {str(e)}")
        return

    types = {
        "Обычный отпуск": {'pattern': 'отпуск', 'days': 14},
        "Больничный": {'pattern': 'б/л', 'days': 7},
        "Учебный отпуск": {'pattern': 'уч.отпуск', 'days': 5}
    }
    
    with st.sidebar.expander("Шаблоны отсутствий"):
        selected = st.selectbox("Тип отсутствия", list(types.keys()))
        start_day = st.number_input("Начальный день", 1, DAYS_IN_MONTH, key='start_day')
        employees = st.multiselect("Сотрудники", employees_list)
        
        if st.button("Применить шаблон"):
            days = types[selected]['days']
            pattern = types[selected]['pattern']
            
            for emp in employees:
                idx = st.session_state.schedule_data[
                    st.session_state.schedule_data['Ф.И.О. мастера смены'] == emp].index[0]
                for i in range(days):
                    day = str(start_day + i)
                    if int(day) <= DAYS_IN_MONTH:
                        st.session_state.schedule_data.at[idx, day] = pattern
            log_action(f"Применен шаблон: {selected} для {len(employees)} сотрудников")
            st.success("Шаблон успешно применен!")

# Умный поиск
def smart_search(df):
    search_term = st.sidebar.text_input("Умный поиск (ФИО/группа/статус)")
    if search_term:
        return df[df.apply(lambda row: any(
            str(search_term).lower() in str(row[col]).lower() 
            for col in ['Ф.И.О. мастера смены', 'ГР №', 'Статус']
        ), axis=1)]
    return df

# Оповещения
def check_upcoming_events(df):
    today = datetime.now().day
    alerts = []
    for _, row in df.iterrows():
        for day in range(today, min(today+3, DAYS_IN_MONTH)):
            val = row.get(str(day), '')
            if val in STATUS_COLORS:
                alerts.append({
                    'date': day,
                    'name': row['Ф.И.О. мастера смены'],
                    'type': val
                })
    
    if alerts:
        with st.expander("🔔 Предстоящие события (3 дня)", expanded=True):
            for alert in alerts:
                st.warning(f"{alert['name']} - {alert['type'].upper()} {alert['date']} числа")

# Дашборд аналитики
def show_analytics(df):
    st.header("📊 Расширенная аналитика")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        analysis_type = st.selectbox("Тип анализа", 
            ["Часы работы", "Переработки", "Статусы"])
        date_range = st.slider("Диапазон дней", 1, DAYS_IN_MONTH, (1, DAYS_IN_MONTH))
    
    with col2:
        if analysis_type == "Часы работы":
            fig = px.bar(df, x='Ф.И.О. мастера смены', y='Факт ФРВ',
                        color='ГР №', barmode='group')
        elif analysis_type == "Переработки":
            fig = px.scatter(df, x='Ф.И.О. мастера смены', y='от ФРВ',
                            size='от ФРВ', color='ГР №')
        else:
            status_counts = df['Статус'].value_counts()
            fig = px.pie(status_counts, values=status_counts.values,
                        names=status_counts.index)
        
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Тепловая карта загруженности")
    heatmap_data = df[[str(d) for d in range(date_range[0], date_range[1]+1)]].applymap(
        lambda x: 0 if x in STATUS_COLORS else float(x) if isinstance(x, (int, float)) else 0)
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=heatmap_data.columns,
        y=df['Ф.И.О. мастера смены'],
        colorscale='Viridis'))
    st.plotly_chart(fig, use_container_width=True)

# Основная функция
def main():
    st.set_page_config(layout="wide", page_title="График работы цеха", page_icon="📅")
    
    # Инициализация данных
    if 'schedule_data' not in st.session_state:
        st.session_state.schedule_data = create_schedule()
    
    # Боковая панель
    st.sidebar.header("Управление")
    absence_template()
    
    # Фильтрация и поиск
    filtered_df = smart_search(st.session_state.schedule_data)
    
    # Сортировка
    sort_col = st.sidebar.selectbox("Сортировать по", filtered_df.columns)
    sort_order = st.sidebar.radio("Порядок сортировки", ["По возрастанию", "По убыванию"])
    filtered_df = filtered_df.sort_values(by=sort_col, ascending=sort_order == "По возрастанию")
    
    # Группировка
    group_by = st.sidebar.selectbox("Группировать по", 
        ["Группам", "Статусам", "Переработкам"])
    
    # Основной интерфейс
    st.title("📅 Управление графиком работы цеха МиЖ ГЛФ")
    check_upcoming_events(filtered_df)
    
    # Редактирование данных
    st.header("Табель учета рабочего времени")
    edited_df = st.data_editor(
        filtered_df.style.apply(style_cells, axis=1),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Ф.И.О. мастера смены": st.column_config.TextColumn(required=True),
            "ГР №": st.column_config.SelectboxColumn(options=WORK_GROUPS)
        },
        key="data_editor"
    )
    
    # Аналитика
    show_analytics(edited_df)
    
    # Экспорт
    st.sidebar.header("Экспорт данных")
    export_format = st.sidebar.selectbox("Формат экспорта", ["Excel", "CSV"])
    
    if st.sidebar.button("Экспортировать данные"):
        output = BytesIO()
        if export_format == "Excel":
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                edited_df.to_excel(writer, index=False)
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            file_ext = "xlsx"
        else:
            output.write(edited_df.to_csv(index=False).encode('utf-8'))
            mime_type = "text/csv"
            file_ext = "csv"
        
        st.sidebar.download_button(
            label=f"Скачать {export_format}",
            data=output.getvalue(),
            file_name=f"график_работы_{datetime.now().strftime('%Y%m%d')}.{file_ext}",
            mime=mime_type
        )
        log_action(f"Экспорт данных в формате {export_format}")

def create_schedule():
    employees = [
        EmployeeSchedule("Феоктистова Е.А.", "ГР1", "График1", {'12': "ГО", '27': '4'}),
        EmployeeSchedule("Третьяков А.И.", "ГР1", "График1"),
        EmployeeSchedule("Грачева Т.В.", "ГР1", "График1"),
        EmployeeSchedule("Белоусов А.В.", "ГР1", "График1", {'12': "ГО"}),
        EmployeeSchedule("Давыдова С.В.", "ГР1", "График1"),
        EmployeeSchedule("Саранцев А.Н. ученик", "ГР1", "График1", {'6': "ув"}),
        EmployeeSchedule("Панфилов А.В.", "ГР2", "График2", {'22': "го"}),
        EmployeeSchedule("Свиридов А.О. (стажер)", "ГР2", "График2"),
        EmployeeSchedule("Смирнов Н.Н.", "ГР2", "График2"),
        EmployeeSchedule("Синякина С.А.", "ГР2", "График2"),
        EmployeeSchedule("Пантюхин А.Д.", "ГР2", "График2", {'23': "го"}),
        EmployeeSchedule("Давыдова О.И.", "ГР2", "График2"),
        EmployeeSchedule("Роменский Р.С.", "ГР2", "График2"),
        EmployeeSchedule("Лукашенкова С.В.", "ГР3", "График3"),
        EmployeeSchedule("Раку О.А.", "ГР3", "График3", {'8': "б/л"}),
        EmployeeSchedule("Михеева А.В.", "ГР3", "График3", {'15': "ГО"}),
        EmployeeSchedule("Антипенко В.Н.", "ГР3", "График3"),
        EmployeeSchedule("Юдина И.Е.", "ГР4", "График4"),
        EmployeeSchedule("Лисовская Т.А.", "ГР4", "График4", {'4': "б/л"}),
        EmployeeSchedule("Галкина В.А.", "ГР4", "График4", {'11': "б/л"}),
        EmployeeSchedule("Незбудеев Д.С.", "ГР4", "График4"),
        EmployeeSchedule("Смоляков А.А.", "ГР4", "График4", {'12': "ГО"}),
        EmployeeSchedule("Долгоаршиннных Т.Р.", "ГР4", "График4"),
        EmployeeSchedule("Подгорбунский Д.А.", "офис", "Офис")
    ]
    return pd.DataFrame([e.generate_schedule() for e in employees])

if __name__ == "__main__":
    main()
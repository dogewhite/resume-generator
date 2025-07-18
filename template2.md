
Resume
企业名称：                                             
申请职位： 
推荐日期：{{ today_time }}                                      
推荐顾问：
分析小结：
匹配程度：{{ match_point }}
{{ match_reason }}
优势分析：
{% for g in pros %}
{{ g }}
{% endfor %}
劣势分析：
{% for b in cons %}
{{ b }}
{% endfor %}
潜在风险：
{% for t in threats %}
{{ t }}
{% endfor %}
基本信息：
姓    名：{{ basic_info.chinese_name }}
性    别：{{ basic_info.gender }}
出生年月：{{ basic_info.birth_date }} 
婚姻状况：{{ basic_info.marital_status }} 
户 籍 地：{{ basic_info.native_place }} 
居 住 地：{{ basic_info.current_city }}  
邮    箱：{{ basic_info.email }}
联系电话：{{ basic_info.phone }} 
目前待遇：{{ basic_info.current_salary }}
期望待遇：{{ basic_info.expect_salary }}
到岗日期：
学历信息：
{% for education in education_experiences %}
在校时间：{{ education.start_date }} - {{ education.end_date }} 
学校名称：{{ education.school }}   
专业：{{ education.major }}    
学位：本科/硕士/博士等：{{ education.degree }}
{% endfor %}

工作经历：
{% for work in work_experiences %}
公司名称：{{ work.company_name }}
企业介绍：{{ work.company_intro }}
工作时间：{{ work.start_date }}-{{ work.end_date }}
工作地点：{{ work.company_location }}
岗位职务：{{ work.position }}
工作描述：{{ work.job_description }}
离职原因：
{% endfor %}
项目经验：
{% for project in project_experiences %}
项目名称：{{ project.project_name }}
职位：{{ project.role }}
工作时间：{{ project.start_date }}--{{ project.end_date }}
项目内容：{{ project.project_intro }}
项目成就: {{ project.project_achievements }}
{% endfor %}

附加信息：
获奖证书:{{ add_info.certificates }}
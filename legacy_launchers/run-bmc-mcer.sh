#!/bin/bash
echo "run-bmc-mcer-pr.sh"
SEND_THREAD_NUM=10  ## 10个8线程
tmp_fifofile="/tmp/$$.fifo" 
mkfifo "$tmp_fifofile" 
exec 6<>"$tmp_fifofile" 
rm $tmp_fifofile

# 初始化并发槽位
for i in $(seq 1 $SEND_THREAD_NUM)
do
	echo 
done >&6

# 基础配置（修复未定义变量问题）
base_dir="/home/wudl"  

instance_hwmcc2015=$base_dir"/ModelChecker/hwmcc2015"

res_modle_checker2=$base_dir"/data/res/bmc_test/mcer_20241127_5000_8thread"

# 限制CPU时间
ulimit -t 20000

# 启用的数据集
all_datas=($instance_hwmcc2015)

# 遍历数据集
for((i=0;i<${#all_datas[*]};i++))
do
	instance=${all_datas[$i]}
	res_solver_ins=$res_modle_checker2
	
	# 创建结果目录（仅执行一次）
	if [ ! -d "$res_solver_ins" ]; then
	 	mkdir -p $res_solver_ins
	fi
	
	# 遍历样本文件（随机顺序）
	for file in `cat $instance/samples/all.txt | shuf`
	do
		echo "开始执行: $file"
		# 占用并发槽位
		read -u 6
		{
			# 定义错误日志文件
			error_log=$res_solver_ins/$file.error
			# 检查工具目录是否存在
			if [ ! -d "/home/wudl/ModelChecker/modelchecker" ]; then
				echo "工具目录不存在" > $error_log
				echo >&6
				continue
			fi
			# 检查样本文件是否存在
			if [ ! -f "$instance/data/$file" ]; then
				echo "样本文件不存在: $instance/data/$file" > $error_log
				echo >&6
				continue
			fi
			# 执行模型检查命令
			cd /home/wudl/ModelChecker/modelchecker && \
			./modelchecker -bmc 4 $instance/data/$file | gnomon
			# 记录执行状态
			if [ $? -eq 0 ]; then
				echo "成功完成: $file" >&2
			else
				echo "执行失败: $file" > $error_log
			fi
			# 释放并发槽位
			echo >&6
		} >$res_solver_ins/$file 2>$res_solver_ins/$file.stderr &
	done
done

# 等待所有后台进程完成
wait
echo "所有任务执行完成"
exit 0
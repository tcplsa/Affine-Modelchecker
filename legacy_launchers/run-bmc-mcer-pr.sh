# !/bin/bash
echo "run-bmc-mcer-pr.sh"
SEND_THREAD_NUM=10  ## 10个8线程
tmp_fifofile="/tmp/$$.fifo" # 脚本运行的当前进程ID号作为文件名
mkfifo "$tmp_fifofile" # 新建一个随机fifo管道文件
exec 6<>"$tmp_fifofile" # 定义文件描述符6指向这个fifo管道文件
rm $tmp_fifofile
for i in $(seq 1 $SEND_THREAD_NUM)
do
	echo # for循环 往 fifo管道文件中写入 $SEND_THREAD_NUM 个空行
done >&6

base_dir="/home/wudl"  

instance_hwmcc2015=$base_dir"/ModelChecker/hwmcc2015"
# instance_hwmcc2015_abc=$base_dir"/data/MC/hwmcc2015-abc"
# instance_hwmcc2017=$base_dir"/data/MC/hwmcc2017"
# instance_hwmcc2017_abc=$base_dir"/data/MC/hwmcc2017-abc"
# instance_hwmcc2020=$base_dir"/data/MC/hwmcc2020"
# instance_hwmcc2020_abc=$base_dir"/data/MC/hwmcc2020-abc"
# instance_hwmcc2019_aigmove=$base_dir"/data/MC/hwmcc2019-aigmove"
# instance_hwmcc2020_aigmove=$base_dir"/data/MC/hwmcc2020-aigmove"
# instance_hwmcc2024_aigmove=$base_dir"/data/MC/hwmcc2024-aigmove"

# res_modle_checker=$base_dir"/data/res/bmc_test/mcer_20241127_5000"
res_modle_checker2=$base_dir"/data/res/bmc_test/mcer_20241127_5000_8thread"

ulimit -t 20000

#all_datas=($instance_hwmcc2015 $instance_hwmcc2017)
#all_datas=($instance_hwmcc2019_aigmove $instance_hwmcc2020_aigmove $instance_hwmcc2024_aigmove)
all_datas=($instance_hwmcc2024_aigmove)

for((i=0;i<${#all_datas[*]};i++))
do
	instance=${all_datas[$i]}

    # tmplate begin
	res_solver_ins=$res_modle_checker2
	if [ ! -d "$res_solver_ins" ]; then
	 	mkdir -p $res_solver_ins
	fi
	for file in `cat $instance/samples/all.txt | shuf`
	do
		echo $file
		if [ ! -d "$res_solver_ins" ]; then
	 		mkdir -p $res_solver_ins
		fi
		touch $res_solver_ins/$file
		read -u 6
		{
			cd /home/wudl/ModelChecker/modelchecker
			./modelchecker -bmc 4 $instance/data/$file | gnomon # ./modelchecker -bmc 4 /home/wudl/data/MC/hwmcc2024-aigmove
			echo "modelchecker finish BMCparallel" $file >&2
			echo >&6
		} >$res_solver_ins/$file  &
	done
    #template end
done

exit 0

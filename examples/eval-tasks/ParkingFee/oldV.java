public class oldV {
    // the first 30 minutes are free; then 500 for each started 10 minutes,
    // at most 10000; members pay half of that
    public static double snippet(int minutes, int member) {
        int fee = 0;
        int units = 0;
        if (minutes > 30) {
            units = (minutes - 30 + 9) / 10;
            fee = units * 500;
            if (fee > 10000) {
                fee = 10000;
            }
            if (member == 1) {
                fee = fee / 2;
            }
        }
        return fee;
    }
}

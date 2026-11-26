public class newV {
    public static double snippet(int minutes, int member) {
        int fee = 0;
        int units = 0;
        if (minutes > 30) {
            units = (minutes - 30) / 10 + 1;
        }
        fee = units * 500;
        if (member == 1) {
            fee = fee / 2;
        }
        fee = Math.min(fee, 10000);
        return fee;
    }
}

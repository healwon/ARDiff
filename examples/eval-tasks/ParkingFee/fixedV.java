public class fixedV {
    public static double snippet(int minutes, int member) {
        int fee = 0;
        int units = 0;
        if (minutes > 30) {
            units = (minutes - 30 + 9) / 10;
        }
        fee = units * 500;
        fee = Math.min(fee, 10000);
        if (member == 1) {
            fee = fee / 2;
        }
        return fee;
    }
}

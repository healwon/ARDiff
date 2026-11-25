public class newV {
    // refactored for readability: billable minutes first, then the price, the member discount and the cap
    public static double snippet(int minutes, int member) {
        int billable = 0;
        int fee = 0;
        billable = Math.max(0, minutes - 30);
        if (billable > 0) {
            fee = (billable / 10 + 1) * 500;
        }
        if (member == 1) {
            fee = fee / 2;
        }
        fee = Math.min(fee, 10000);
        return fee;
    }
}

public class fixedV {
    // reference fix: round up with (billable + 9) / 10, and cap before the member discount
    public static double snippet(int minutes, int member) {
        int billable = 0;
        int fee = 0;
        billable = Math.max(0, minutes - 30);
        if (billable > 0) {
            fee = (billable + 9) / 10 * 500;
        }
        fee = Math.min(fee, 10000);
        if (member == 1) {
            fee = fee / 2;
        }
        return fee;
    }
}

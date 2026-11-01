public class fixedV {
    // reference fix: round the overtime pay once, not per hour
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        int regular = 0;
        int over = 0;
        regular = Math.min(hours, 40);
        over = Math.max(hours - 40, 0);
        pay = regular * rate + over * rate * 3 / 2;
        if (holiday == 1) {
            pay = hours * rate * 2;
        }
        return pay;
    }
}

public class fixedV {
    // reference fix: 1.5 times the rate is rounded down per hour, as before
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        int regular = 0;
        int over = 0;
        regular = Math.min(hours, 40);
        over = Math.max(hours - 40, 0);
        pay = regular * rate + over * (rate * 3 / 2);
        return pay;
    }
}

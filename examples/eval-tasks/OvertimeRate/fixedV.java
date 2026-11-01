public class fixedV {
    // reference fix: no premium on a holiday; otherwise the premium per overtime hour is 1.5 x rate rounded down, minus the rate (as before)
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        int regular = 0;
        int over = 0;
        over = Math.max(hours - 40, 0);
        pay = hours * rate + (holiday == 1 ? 0 : over * (rate * 3 / 2 - rate));
        if (holiday == 1) {
            pay = pay * 2;
        }
        return pay;
    }
}

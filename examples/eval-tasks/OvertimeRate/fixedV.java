public class fixedV {
    // reference fix: the premium per overtime hour rounded as before, and no holiday rule
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        int regular = 0;
        int over = 0;
        over = Math.max(hours - 40, 0);
        pay = hours * rate + over * (rate * 3 / 2 - rate);
        return pay;
    }
}

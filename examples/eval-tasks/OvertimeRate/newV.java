public class newV {
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        int regular = 0;
        int over = 0;
        over = Math.max(hours - 40, 0);
        pay = hours * rate + over * rate / 2;
        if (holiday == 1) {
            pay = pay * 2;
        }
        return pay;
    }
}
